import { get, put } from './client.js'

/** @returns {Promise<{boxes:any[], image_labels:string[], version:number}>} */
export const getAnnotations = (expId, imageId) => get(`/experiments/${expId}/images/${imageId}/annotations`)

/** Full-set save with optimistic concurrency. Throws ApiError(409,'conflict') on mismatch. */
export const saveAnnotations = (expId, imageId, { boxes, image_labels, version }) =>
  put(`/experiments/${expId}/images/${imageId}/annotations`, { boxes, image_labels }, { headers: { 'If-Match': String(version) } })
