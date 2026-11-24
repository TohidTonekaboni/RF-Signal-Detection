import { get, post, patch } from './client.js'
export const listUsers = () => get('/users')
export const createUser = (b) => post('/users', b)
export const updateUser = (id, b) => patch(`/users/${id}`, b)
export const resetPassword = (id) => post(`/users/${id}/reset-password`)
export const listAudit = (params) => get('/audit', params)
