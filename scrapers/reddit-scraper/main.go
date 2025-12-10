package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/joho/godotenv"
	"github.com/segmentio/kafka-go"
	log "github.com/sirupsen/logrus"
	"golang.org/x/time/rate"
)

const maxWorkers = 5 // <-- you asked for 5 workers

// Configuration holds all scraper settings
type Configuration struct {
	RedditClientID     string
	RedditClientSecret string
	RedditUserAgent    string
	KafkaBootstrap     string
	KafkaTopic         string
	RateLimit          int
	ScrapeInterval     time.Duration
}

// RedditAuth represents OAuth token response
type RedditAuth struct {
	AccessToken string `json:"access_token"`
	TokenType   string `json:"token_type"`
	ExpiresIn   int    `json:"expires_in"`
	Scope       string `json:"scope"`
}

// RedditPost represents a single Reddit post
type RedditPost struct {
	ID          string  `json:"id"`
	Title       string  `json:"title"`
	Selftext    string  `json:"selftext"`
	Author      string  `json:"author"`
	Subreddit   string  `json:"subreddit"`
	Score       int     `json:"score"`
	NumComments int     `json:"num_comments"`
	CreatedUTC  float64 `json:"created_utc"`
	URL         string  `json:"url"`
	Permalink   string  `json:"permalink"`
}

// RedditComment represents a Reddit comment
type RedditComment struct {
	ID         string  `json:"id"`
	Body       string  `json:"body"`
	Author     string  `json:"author"`
	Score      int     `json:"score"`
	CreatedUTC float64 `json:"created_utc"`
	ParentID   string  `json:"parent_id"`
	PostID     string  `json:"post_id"`
}

// ScrapedData represents data to be sent to Kafka
type ScrapedData struct {
	Source    string            `json:"source"`
	Product   string            `json:"product"`
	DataType  string            `json:"data_type"`
	Content   string            `json:"content"`
	Title     string            `json:"title,omitempty"`
	Author    string            `json:"author"`
	Score     int               `json:"score"`
	URL       string            `json:"url"`
	Subreddit string            `json:"subreddit,omitempty"`
	CreatedAt time.Time         `json:"created_at"`
	ScrapedAt time.Time         `json:"scraped_at"`
	Metadata  map[string]string `json:"metadata"`
}

// ScrapeRequest represents a product scrape request from API
type ScrapeRequest struct {
	Product    string   `json:"product"`
	Subreddits []string `json:"subreddits"`
	Keywords   []string `json:"keywords"`
}

// Task used by worker pool
type Task struct {
	Product   string
	Subreddit string
	Keyword   string
}

// RedditScraper handles Reddit API interactions
type RedditScraper struct {
	config      Configuration
	accessToken string
	tokenExpiry time.Time
	httpClient  *http.Client
	writer      *kafka.Writer
	limiter     *rate.Limiter
	mu          sync.RWMutex
}

func NewRedditScraper(config Configuration) (*RedditScraper, error) {
	writer := &kafka.Writer{
		Addr:         kafka.TCP(config.KafkaBootstrap),
		Topic:        config.KafkaTopic,
		Balancer:     &kafka.LeastBytes{},
		BatchTimeout: 10 * time.Millisecond,
		RequiredAcks: kafka.RequireAll,
		Async:        false,
	}

	limiter := rate.NewLimiter(rate.Limit(float64(config.RateLimit)/60.0), config.RateLimit/10)

	return &RedditScraper{
		config:     config,
		httpClient: &http.Client{Timeout: 30 * time.Second},
		writer:     writer,
		limiter:    limiter,
	}, nil
}

func (s *RedditScraper) authenticate() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.accessToken != "" && time.Now().Before(s.tokenExpiry) {
		return nil
	}

	data := url.Values{}
	data.Set("grant_type", "client_credentials")

	req, err := http.NewRequest("POST", "https://www.reddit.com/api/v1/access_token", strings.NewReader(data.Encode()))
	if err != nil {
		return fmt.Errorf("failed to create auth request: %w", err)
	}

	req.SetBasicAuth(s.config.RedditClientID, s.config.RedditClientSecret)
	req.Header.Set("User-Agent", s.config.RedditUserAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("auth request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("auth failed with status %d: %s", resp.StatusCode, string(body))
	}

	var auth RedditAuth
	if err := json.NewDecoder(resp.Body).Decode(&auth); err != nil {
		return fmt.Errorf("failed to decode auth response: %w", err)
	}

	s.accessToken = auth.AccessToken
	// subtract a minute as buffer
	s.tokenExpiry = time.Now().Add(time.Duration(auth.ExpiresIn-60) * time.Second)

	log.Info("Successfully authenticated with Reddit API")
	return nil
}

func (s *RedditScraper) makeRequest(endpoint string) ([]byte, error) {
	ctx := context.Background()

	// Rate limiter wait
	if err := s.limiter.Wait(ctx); err != nil {
		return nil, fmt.Errorf("rate limiter error: %w", err)
	}

	if err := s.authenticate(); err != nil {
		return nil, err
	}

	s.mu.RLock()
	token := s.accessToken
	s.mu.RUnlock()

	req, err := http.NewRequest("GET", "https://oauth.reddit.com"+endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("User-Agent", s.config.RedditUserAgent)

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		// force re-auth
		s.mu.Lock()
		s.accessToken = ""
		s.mu.Unlock()
		return nil, fmt.Errorf("token expired, retry required")
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	return io.ReadAll(resp.Body)
}

func (s *RedditScraper) searchPosts(query string, subreddit string, limit int) ([]RedditPost, error) {
	endpoint := fmt.Sprintf("/r/%s/search?q=%s&limit=%d&sort=new&restrict_sr=on&type=link",
		subreddit, url.QueryEscape(query), limit)

	body, err := s.makeRequest(endpoint)
	if err != nil {
		return nil, err
	}

	var result struct {
		Data struct {
			Children []struct {
				Data RedditPost `json:"data"`
			} `json:"children"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	posts := make([]RedditPost, len(result.Data.Children))
	for i, child := range result.Data.Children {
		posts[i] = child.Data
	}

	return posts, nil
}

func (s *RedditScraper) getComments(postID string, subreddit string, limit int) ([]RedditComment, error) {
	endpoint := fmt.Sprintf("/r/%s/comments/%s?limit=%d&sort=best&depth=2",
		subreddit, postID, limit)

	body, err := s.makeRequest(endpoint)
	if err != nil {
		return nil, err
	}

	var result []json.RawMessage
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	if len(result) < 2 {
		return nil, nil
	}

	var commentsData struct {
		Data struct {
			Children []struct {
				Kind string `json:"kind"`
				Data struct {
					ID         string  `json:"id"`
					Body       string  `json:"body"`
					Author     string  `json:"author"`
					Score      int     `json:"score"`
					CreatedUTC float64 `json:"created_utc"`
					ParentID   string  `json:"parent_id"`
				} `json:"data"`
			} `json:"children"`
		} `json:"data"`
	}

	if err := json.Unmarshal(result[1], &commentsData); err != nil {
		return nil, fmt.Errorf("failed to parse comments: %w", err)
	}

	comments := make([]RedditComment, 0)
	for _, child := range commentsData.Data.Children {
		if child.Kind == "t1" && child.Data.Body != "" && child.Data.Body != "[deleted]" {
			comments = append(comments, RedditComment{
				ID:         child.Data.ID,
				Body:       child.Data.Body,
				Author:     child.Data.Author,
				Score:      child.Data.Score,
				CreatedUTC: child.Data.CreatedUTC,
				ParentID:   child.Data.ParentID,
				PostID:     postID,
			})
		}
	}

	return comments, nil
}

func (s *RedditScraper) sendToKafka(data ScrapedData) error {
	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal data: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	err = s.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(data.Product),
		Value: jsonData,
		Time:  time.Now(),
	})

	if err != nil {
		return fmt.Errorf("failed to write message to Kafka: %w", err)
	}

	return nil
}

func (s *RedditScraper) processPost(product, keyword, subreddit string, post RedditPost) {
	// Skip empty posts
	if post.Title == "" && post.Selftext == "" {
		return
	}

	content := post.Selftext
	if content == "" {
		content = post.Title
	}

	scrapedPost := ScrapedData{
		Source:    "reddit",
		Product:   product,
		DataType:  "post",
		Content:   content,
		Title:     post.Title,
		Author:    post.Author,
		Score:     post.Score,
		URL:       "https://reddit.com" + post.Permalink,
		Subreddit: subreddit,
		CreatedAt: time.Unix(int64(post.CreatedUTC), 0),
		ScrapedAt: time.Now(),
		Metadata: map[string]string{
			"post_id":      post.ID,
			"num_comments": fmt.Sprintf("%d", post.NumComments),
			"keyword":      keyword,
		},
	}

	if err := s.sendToKafka(scrapedPost); err != nil {
		log.WithError(err).Warn("Failed to send post to Kafka")
	}

	// Fetch comments (sequentially here to avoid lots of concurrent comment fetches)
	if post.NumComments > 5 {
		comments, err := s.getComments(post.ID, subreddit, 20)
		if err != nil {
			log.WithError(err).Warn("Failed to fetch comments")
			return
		}

		for _, comment := range comments {
			scrapedComment := ScrapedData{
				Source:    "reddit",
				Product:   product,
				DataType:  "comment",
				Content:   comment.Body,
				Author:    comment.Author,
				Score:     comment.Score,
				URL:       "https://reddit.com" + post.Permalink,
				Subreddit: subreddit,
				CreatedAt: time.Unix(int64(comment.CreatedUTC), 0),
				ScrapedAt: time.Now(),
				Metadata: map[string]string{
					"comment_id": comment.ID,
					"post_id":    post.ID,
					"parent_id":  comment.ParentID,
				},
			}
			if err := s.sendToKafka(scrapedComment); err != nil {
				log.WithError(err).Warn("Failed to send comment to Kafka")
			}
		}
	}
}

// scrapeKeywordForSubreddit handles the work for a single subreddit+keyword combo.
// It limits per-task concurrency for processing posts using a small semaphore.
func (s *RedditScraper) scrapeKeywordForSubreddit(product, subreddit, keyword string) {
	searchQuery := fmt.Sprintf("\"%s\" AND %s", product, keyword)

	posts, err := s.searchPosts(searchQuery, subreddit, 25)
	if err != nil {
		log.WithError(err).WithFields(log.Fields{
			"subreddit": subreddit,
			"keyword":   keyword,
		}).Warn("Search failed")
		return
	}

	// Small semaphore to limit how many posts we process concurrently per task.
	// This prevents a single task from spawning too many goroutines.
	const perTaskConcurrency = 3
	sem := make(chan struct{}, perTaskConcurrency)

	var wg sync.WaitGroup
	for _, p := range posts {
		post := p
		sem <- struct{}{}
		wg.Add(1)

		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			s.processPost(product, keyword, subreddit, post)
		}()
	}

	wg.Wait()
}

// ScrapeProduct enqueues tasks (subreddit × keyword) and processes them with a worker pool.
func (s *RedditScraper) ScrapeProduct(request ScrapeRequest) error {
	log.WithFields(log.Fields{
		"product":    request.Product,
		"subreddits": request.Subreddits,
		"keywords":   request.Keywords,
	}).Info("Starting parallel scrape (worker pool)")

	taskCount := len(request.Subreddits) * len(request.Keywords)
	taskChan := make(chan Task, taskCount)

	var wg sync.WaitGroup

	// Start workers
	for i := 0; i < maxWorkers; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			for task := range taskChan {
				log.WithFields(log.Fields{
					"worker":    workerID,
					"subreddit": task.Subreddit,
					"keyword":   task.Keyword,
				}).Info("Worker picked up task")
				s.scrapeKeywordForSubreddit(task.Product, task.Subreddit, task.Keyword)
			}
		}(i)
	}

	// Enqueue tasks
	for _, sub := range request.Subreddits {
		for _, kw := range request.Keywords {
			taskChan <- Task{
				Product:   request.Product,
				Subreddit: sub,
				Keyword:   kw,
			}
		}
	}

	close(taskChan) // signal workers no more tasks
	wg.Wait()       // wait for all workers to finish

	log.WithFields(log.Fields{
		"product": request.Product,
	}).Info("Completed parallel scrape")

	return nil
}

func (s *RedditScraper) Close() {
	if s.writer != nil {
		s.writer.Close()
	}
}

// HTTP Server for receiving scrape requests
type HTTPServer struct {
	scraper *RedditScraper
}

func NewHTTPServer(scraper *RedditScraper) *HTTPServer {
	return &HTTPServer{scraper: scraper}
}

func (h *HTTPServer) handleScrape(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var request ScrapeRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Default subreddits if none provided
	if len(request.Subreddits) == 0 {
		request.Subreddits = []string{"technology", "gadgets", "samsung", "Android", "samsunggalaxy"}
	}

	// Default keywords if none provided
	if len(request.Keywords) == 0 {
		request.Keywords = []string{"review", "problem", "issue", "help", "question", "experience", "opinion"}
	}

	// Run scrape in background (one goroutine per HTTP request)
	go func() {
		if err := h.scraper.ScrapeProduct(request); err != nil {
			log.WithError(err).Error("Scrape failed")
		}
	}()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "started",
		"product": request.Product,
	})
}

func (h *HTTPServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
}

func loadConfig() Configuration {
	// Try to load .env file
	_ = godotenv.Load()

	rateLimit := 100
	if rl := os.Getenv("SCRAPE_RATE_LIMIT"); rl != "" {
		fmt.Sscanf(rl, "%d", &rateLimit)
	}

	interval := 60
	if si := os.Getenv("SCRAPE_INTERVAL_SECONDS"); si != "" {
		fmt.Sscanf(si, "%d", &interval)
	}

	return Configuration{
		RedditClientID:     os.Getenv("REDDIT_CLIENT_ID"),
		RedditClientSecret: os.Getenv("REDDIT_CLIENT_SECRET"),
		RedditUserAgent:    os.Getenv("REDDIT_USER_AGENT"),
		KafkaBootstrap:     getEnvOrDefault("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
		KafkaTopic:         getEnvOrDefault("KAFKA_TOPIC_RAW_DATA", "raw_social_data"),
		RateLimit:          rateLimit,
		ScrapeInterval:     time.Duration(interval) * time.Second,
	}
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func main() {
	log.SetFormatter(&log.JSONFormatter{})
	log.SetLevel(log.InfoLevel)

	config := loadConfig()

	if config.RedditClientID == "" || config.RedditClientSecret == "" {
		log.Fatal("Reddit credentials not configured")
	}

	scraper, err := NewRedditScraper(config)
	if err != nil {
		log.WithError(err).Fatal("Failed to create scraper")
	}
	defer scraper.Close()

	server := NewHTTPServer(scraper)

	http.HandleFunc("/scrape", server.handleScrape)
	http.HandleFunc("/health", server.handleHealth)

	// Graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Info("Starting Reddit scraper server on :8081")
		if err := http.ListenAndServe(":8081", nil); err != nil {
			log.WithError(err).Fatal("Server failed")
		}
	}()

	<-sigChan
	log.Info("Shutting down gracefully...")
}
