import { post, api } from './client.js'
export const login = (username, password) => post('/auth/login', { username, password }, { noRefresh: true })
export const logout = () => post('/auth/logout', undefined, { noRefresh: true })
export const changePassword = (current_password, new_password) => post('/auth/change-password', { current_password, new_password })
export const whoAmI = () => api('GET', '/auth/me')
