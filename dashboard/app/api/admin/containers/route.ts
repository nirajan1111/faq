import { NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'

const execAsync = promisify(exec)

export async function GET() {
  try {
    // Get list of running containers
    const { stdout } = await execAsync(
      'docker ps --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.CreatedAt}}"'
    )

    const containers = stdout
      .trim()
      .split('\n')
      .filter(line => line)
      .map(line => {
        const [id, name, image, status, created] = line.split('|')
        return {
          id: id.trim(),
          name: name.trim(),
          image: image.trim(),
          status: status.toLowerCase().includes('up') ? 'running' : 'stopped',
          created: created.trim()
        }
      })

    return NextResponse.json(containers)
  } catch (error) {
    console.error('Failed to fetch containers:', error)
    return NextResponse.json(
      { error: 'Failed to fetch containers' },
      { status: 500 }
    )
  }
}
