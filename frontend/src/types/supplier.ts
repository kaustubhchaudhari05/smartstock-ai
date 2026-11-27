/** Item of GET /api/suppliers */
export interface Supplier {
  id: number
  name: string
  email: string
  phone: string | null
  address: string | null
  lead_time_days: number
  is_active: boolean
}
