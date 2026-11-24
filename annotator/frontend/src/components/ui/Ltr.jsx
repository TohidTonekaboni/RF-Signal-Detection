/** Bidi-isolate technical values (filenames, frequencies, coordinates) so mixed lines don't scramble. */
export function Ltr({ children, className }) {
  return <bdi dir="ltr" className={className}>{children}</bdi>
}
