import { get, post, put } from './client.js'
export const listExperiments = () => get('/experiments')
export const getExperiment = (id) => get(`/experiments/${id}`)
export const createExperiment = (body) => post('/experiments', body)
export const updateExperiment = (id, body) => put(`/experiments/${id}`, body)
export const getExperimentStats = (id) => get(`/experiments/${id}/stats`)
export const listExperimentImages = (id, params) => get(`/experiments/${id}/images`, params)
