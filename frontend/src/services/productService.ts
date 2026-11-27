import type { Product, ProductCreate, ProductListParams, ProductUpdate } from '../types/product'
import { apiDelete, apiGet, apiPost, apiPut } from './api'

export const listProducts = (params?: ProductListParams) => apiGet<Product[]>('/products', { ...params })

export const getProduct = (id: number) => apiGet<Product>(`/products/${id}`)

export const createProduct = (data: ProductCreate) => apiPost<Product>('/products', data)

/** Partial update: only the fields present in `data` change. */
export const updateProduct = (id: number, data: ProductUpdate) => apiPut<Product>(`/products/${id}`, data)

/** Soft delete (sets is_active = false); returns the product. */
export const deactivateProduct = (id: number) => apiDelete<Product>(`/products/${id}`)

export const reactivateProduct = (id: number) => updateProduct(id, { is_active: true })
