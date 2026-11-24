import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n/index.js'
import { Pagination } from '@/components/ui/Pagination.jsx'

describe.each(['rtl', 'ltr'])('Pagination in %s', (dir) => {
  it('navigates and disables edges', () => {
    const onChange = vi.fn()
    render(<div dir={dir}><Pagination page={1} pageSize={10} total={25} onChange={onChange} /></div>)
    const [prev, next] = screen.getAllByRole('button')
    expect(prev).toBeDisabled()
    fireEvent.click(next)
    expect(onChange).toHaveBeenCalledWith(2)
  })
})
