import { get, post, del } from './client.js'
import { MOCK } from './client.js'
import { mockUpload } from './mock.js'

/** @param {{page?:number,page_size?:number,q?:string,from?:string,to?:string}} params */
export const listImages = (params) => get('/images', params)
export const getImage = (id) => get(`/images/${id}`)
export const deleteImage = (id) => del(`/images/${id}`)

/**
 * Presigned-PUT upload with per-file progress. Resolves with the created image.
 * @param {File} file @param {(pct:number)=>void} onProgress @param {AbortSignal} [signal]
 */
export async function uploadImage(file, onProgress, signal) {
  if (MOCK) return mockUpload(file, onProgress)
  const { image_id, upload_url } = await post('/images/presign', { filename: file.name, content_type: file.type, size: file.size })
  await new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', upload_url)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100))
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error('upload failed')))
    xhr.onerror = () => reject(new Error('upload failed'))
    signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(file)
  })
  return post(`/images/${image_id}/complete`)
}
