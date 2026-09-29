const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export async function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params).toString()}` : ''
  const response = await fetch(`${BASE_URL}${path}${query}`)
  if (!response.ok) {
    throw new Error(`Falha em ${path}: ${response.status}`)
  }
  return response.json() as Promise<T>
}
