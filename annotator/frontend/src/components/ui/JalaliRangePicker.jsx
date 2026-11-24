import DatePicker from 'react-multi-date-picker'
import DateObject from 'react-date-object'
import persian from 'react-date-object/calendars/persian'
import persian_fa from 'react-date-object/locales/persian_fa'
import gregorian from 'react-date-object/calendars/gregorian'
import gregorian_en from 'react-date-object/locales/gregorian_en'
import { useTranslation } from 'react-i18next'

/**
 * Jalali range filter. Wrapped so the date-picker library can be swapped.
 * value / onChange use plain {from, to} Jalali parts: {year, month(1-12), day}.
 */
const toParts = (d) => d && { year: d.year, month: d.month.number, day: d.day }
const toObj = (p, cal, loc) => p && new DateObject({ calendar: cal, locale: loc, year: p.year, month: p.month, day: p.day })

export function JalaliRangePicker({ value, onChange, placeholder }) {
  const { i18n } = useTranslation()
  const fa = i18n.language === 'fa'
  const cal = fa ? persian : gregorian
  const loc = fa ? persian_fa : gregorian_en
  const arr = value?.from ? [toObj(value.from, persian, persian_fa), value.to && toObj(value.to, persian, persian_fa)].filter(Boolean) : []
  return (
    <DatePicker
      range
      calendar={cal}
      locale={loc}
      weekStartDayIndex={fa ? 0 : 1}
      value={arr}
      format="YYYY/MM/DD"
      calendarPosition="bottom-right"
      containerClassName="w-full"
      inputClass="input"
      placeholder={placeholder}
      onChange={(r) => {
        const [a, b] = (r || []).map((d) => d && d.convert(persian, persian_fa))
        onChange(a ? { from: toParts(a), to: b ? toParts(b) : null } : { from: null, to: null })
      }}
      className={document.documentElement.dataset.theme === 'light' ? '' : 'bg-dark'}
    />
  )
}
