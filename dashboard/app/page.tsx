'use client'

import { useState, useEffect } from 'react'
import axios from 'axios'
import {
  Plus,
  RefreshCw,
  Trash2,
  Play,
  MessageSquare,
  Loader2,
  Search,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  AlertCircle,
  CheckCircle,
  Clock,
  Settings
} from 'lucide-react'
import Link from 'next/link'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Product {
  id: string
  name: string
  description?: string
  subreddits: string[]
  keywords: string[]
  category?: string
  created_at: string
  last_scraped?: string
  last_processed?: string
  faq_count: number
  status: string
}

interface FAQ {
  question: string
  answer: string
  category: string
  confidence: number
  sources: string[]
  keywords: string[]
}

interface Stats {
  total_products: number
  total_faq_documents: number
  products_by_status: Record<string, number>
}

export default function Home() {
  const [products, setProducts] = useState<Product[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [faqs, setFaqs] = useState<FAQ[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // New product form state
  const [newProduct, setNewProduct] = useState({
    name: '',
    description: '',
    keywords: 'review,problem,help,question,experience',
    category: ''
  })

  useEffect(() => {
    fetchProducts()
    fetchStats()
  }, [])

  const fetchProducts = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/products`)
      setProducts(response.data)
    } catch (error) {
      console.error('Failed to fetch products:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/stats`)
      setStats(response.data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }

  const fetchFaqs = async (productName: string) => {
    try {
      const response = await axios.get(`${API_URL}/api/faqs/${encodeURIComponent(productName)}`)
      setFaqs(response.data.faqs || [])
    } catch (error) {
      console.error('Failed to fetch FAQs:', error)
      setFaqs([])
    }
  }

  const handleAddProduct = async () => {
    try {
      await axios.post(`${API_URL}/api/products`, {
        name: newProduct.name,
        description: newProduct.description || null,
        keywords: newProduct.keywords.split(',').map(k => k.trim()),
        category: newProduct.category || null
      })
      setShowAddModal(false)
      setNewProduct({ name: '', description: '', keywords: 'review,problem,help,question,experience', category: '' })
      fetchProducts()
      fetchStats()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to add product')
    }
  }

  const handleDeleteProduct = async (id: string) => {
    if (!confirm('Are you sure you want to delete this product?')) return
    try {
      await axios.delete(`${API_URL}/api/products/${id}`)
      fetchProducts()
      fetchStats()
      if (selectedProduct?.id === id) {
        setSelectedProduct(null)
        setFaqs([])
      }
    } catch (error) {
      console.error('Failed to delete product:', error)
    }
  }

  const handleTriggerScrape = async (productId: string) => {
    try {
      await axios.post(`${API_URL}/api/scrape`, { product_id: productId })
      alert('Scraping started!')
      fetchProducts()
    } catch (error) {
      console.error('Failed to trigger scrape:', error)
    }
  }

  const handleGenerateFaqs = async (productId: string) => {
    try {
      await axios.post(`${API_URL}/api/generate-faqs`, { product_id: productId })
      alert('FAQ generation started!')
      fetchProducts()
    } catch (error) {
      console.error('Failed to generate FAQs:', error)
    }
  }

  const handleRunPipeline = async (productId: string) => {
    try {
      await axios.post(`${API_URL}/api/pipeline/${productId}`)
      alert('Full pipeline started! This may take several minutes.')
      fetchProducts()
    } catch (error) {
      console.error('Failed to run pipeline:', error)
    }
  }

  const handleSelectProduct = (product: Product) => {
    setSelectedProduct(product)
    if (product.faq_count > 0) {
      fetchFaqs(product.name)
    } else {
      setFaqs([])
    }
  }

  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { color: string; icon: React.ReactNode }> = {
      pending: { color: 'bg-gray-100 text-gray-800', icon: <Clock className="w-3 h-3" /> },
      scraping: { color: 'bg-blue-100 text-blue-800', icon: <Loader2 className="w-3 h-3 animate-spin" /> },
      processing: { color: 'bg-yellow-100 text-yellow-800', icon: <Loader2 className="w-3 h-3 animate-spin" /> },
      generating: { color: 'bg-purple-100 text-purple-800', icon: <Loader2 className="w-3 h-3 animate-spin" /> },
      completed: { color: 'bg-green-100 text-green-800', icon: <CheckCircle className="w-3 h-3" /> },
      error: { color: 'bg-red-100 text-red-800', icon: <AlertCircle className="w-3 h-3" /> }
    }
    const config = statusConfig[status] || statusConfig.pending
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
        {config.icon}
        {status}
      </span>
    )
  }

  const filteredFaqs = faqs.filter(faq => 
    faq.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
    faq.answer.toLowerCase().includes(searchQuery.toLowerCase()) ||
    faq.category.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    )
  }

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">FAQ Generation Dashboard</h1>
              <p className="text-sm text-gray-500 mt-1">Generate FAQs from social media discussions</p>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href="/admin"
                className="inline-flex items-center gap-2 px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                <Settings className="w-4 h-4" />
                Admin
              </Link>
              <button
                onClick={() => setShowAddModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Product
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Stats */}
      {stats && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl shadow-sm p-4 border">
              <p className="text-sm text-gray-500">Total Products</p>
              <p className="text-2xl font-bold text-gray-900">{stats.total_products}</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm p-4 border">
              <p className="text-sm text-gray-500">FAQ Documents</p>
              <p className="text-2xl font-bold text-gray-900">{stats.total_faq_documents}</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm p-4 border">
              <p className="text-sm text-gray-500">Completed</p>
              <p className="text-2xl font-bold text-green-600">{stats.products_by_status.completed || 0}</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm p-4 border">
              <p className="text-sm text-gray-500">In Progress</p>
              <p className="text-2xl font-bold text-blue-600">
                {(stats.products_by_status.scraping || 0) + 
                 (stats.products_by_status.processing || 0) + 
                 (stats.products_by_status.generating || 0)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Products List */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-sm border">
              <div className="p-4 border-b">
                <h2 className="font-semibold text-gray-900">Products</h2>
              </div>
              <div className="divide-y max-h-[600px] overflow-y-auto">
                {products.length === 0 ? (
                  <div className="p-8 text-center text-gray-500">
                    <MessageSquare className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                    <p>No products yet</p>
                    <p className="text-sm">Add a product to get started</p>
                  </div>
                ) : (
                  products.map((product) => (
                    <div
                      key={product.id}
                      className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                        selectedProduct?.id === product.id ? 'bg-primary-50 border-l-4 border-primary-600' : ''
                      }`}
                      onClick={() => handleSelectProduct(product)}
                    >
                      <div className="flex justify-between items-start">
                        <div className="flex-1 min-w-0">
                          <h3 className="font-medium text-gray-900 truncate">{product.name}</h3>
                          <p className="text-sm text-gray-500 mt-1">
                            {product.faq_count} FAQs • {product.subreddits.length} subreddits
                          </p>
                          <div className="mt-2">
                            {getStatusBadge(product.status)}
                          </div>
                        </div>
                        <div className="flex gap-1 ml-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleRunPipeline(product.id)
                            }}
                            className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded"
                            title="Run full pipeline"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDeleteProduct(product.id)
                            }}
                            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                            title="Delete product"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* FAQs Display */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl shadow-sm border">
              {selectedProduct ? (
                <>
                  <div className="p-4 border-b">
                    <div className="flex justify-between items-start">
                      <div>
                        <h2 className="font-semibold text-gray-900">{selectedProduct.name}</h2>
                        <p className="text-sm text-gray-500 mt-1">
                          {selectedProduct.description || 'No description'}
                        </p>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {selectedProduct.subreddits.map((sub, i) => (
                            <span key={i} className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded text-xs">
                              r/{sub}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleTriggerScrape(selectedProduct.id)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100"
                        >
                          <RefreshCw className="w-3 h-3" />
                          Scrape
                        </button>
                        <button
                          onClick={() => handleGenerateFaqs(selectedProduct.id)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100"
                        >
                          <MessageSquare className="w-3 h-3" />
                          Generate FAQs
                        </button>
                      </div>
                    </div>
                    
                    {/* Search FAQs */}
                    {faqs.length > 0 && (
                      <div className="mt-4 relative">
                        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                          type="text"
                          placeholder="Search FAQs..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                        />
                      </div>
                    )}
                  </div>

                  <div className="divide-y max-h-[500px] overflow-y-auto">
                    {filteredFaqs.length === 0 ? (
                      <div className="p-8 text-center text-gray-500">
                        <MessageSquare className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                        <p>No FAQs generated yet</p>
                        <p className="text-sm">Click "Generate FAQs" to create FAQs from scraped data</p>
                      </div>
                    ) : (
                      filteredFaqs.map((faq, index) => (
                        <div key={index} className="p-4">
                          <button
                            onClick={() => setExpandedFaq(expandedFaq === index ? null : index)}
                            className="w-full text-left"
                          >
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                                    {faq.category}
                                  </span>
                                  <span className="text-xs text-gray-400">
                                    {Math.round(faq.confidence * 100)}% confidence
                                  </span>
                                </div>
                                <h3 className="font-medium text-gray-900">{faq.question}</h3>
                              </div>
                              {expandedFaq === index ? (
                                <ChevronUp className="w-5 h-5 text-gray-400" />
                              ) : (
                                <ChevronDown className="w-5 h-5 text-gray-400" />
                              )}
                            </div>
                          </button>
                          
                          {expandedFaq === index && (
                            <div className="mt-3 pl-4 border-l-2 border-primary-200">
                              <p className="text-gray-700 whitespace-pre-wrap">{faq.answer}</p>
                              
                              {faq.keywords.length > 0 && (
                                <div className="mt-3 flex flex-wrap gap-1">
                                  {faq.keywords.map((keyword, ki) => (
                                    <span key={ki} className="px-2 py-0.5 bg-primary-50 text-primary-700 rounded text-xs">
                                      {keyword}
                                    </span>
                                  ))}
                                </div>
                              )}
                              
                              {faq.sources.length > 0 && (
                                <div className="mt-3">
                                  <p className="text-xs text-gray-500 mb-1">Sources:</p>
                                  {faq.sources.slice(0, 2).map((source, si) => (
                                    <a
                                      key={si}
                                      href={source}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="inline-flex items-center gap-1 text-xs text-primary-600 hover:underline mr-3"
                                    >
                                      <ExternalLink className="w-3 h-3" />
                                      Source {si + 1}
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </>
              ) : (
                <div className="p-8 text-center text-gray-500">
                  <MessageSquare className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                  <p>Select a product to view FAQs</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Add Product Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
            <div className="p-4 border-b">
              <h2 className="text-lg font-semibold text-gray-900">Add New Product</h2>
              <p className="text-xs text-gray-500 mt-1">Relevant subreddits will be automatically discovered</p>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Product Name *
                </label>
                <input
                  type="text"
                  value={newProduct.name}
                  onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
                  placeholder="e.g., Samsung Galaxy S24"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  value={newProduct.description}
                  onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })}
                  placeholder="Brief description of the product"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  rows={2}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Keywords (comma-separated)
                </label>
                <input
                  type="text"
                  value={newProduct.keywords}
                  onChange={(e) => setNewProduct({ ...newProduct, keywords: e.target.value })}
                  placeholder="review,problem,help,question"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Category
                </label>
                <input
                  type="text"
                  value={newProduct.category}
                  onChange={(e) => setNewProduct({ ...newProduct, category: e.target.value })}
                  placeholder="e.g., Smartphones"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            </div>
            <div className="p-4 border-t flex justify-end gap-2">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddProduct}
                disabled={!newProduct.name.trim()}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Add Product
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
