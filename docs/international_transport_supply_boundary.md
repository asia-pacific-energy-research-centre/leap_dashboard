# International transport supply boundary

International marine and aviation bunkers are outside domestic final demand.
The Common ESTO dashboard therefore routes codes `04` and `05` to the Supply
page and includes the signed combined `04-05` comparison row in both Energy
balance overview supply composition charts. The overview uses that common row
rather than also summing its retained `04` and `05` source children, which
would count bunkers twice. The detailed children remain visible on Supply.

LEAP's `All demand aggregated/International transport` placeholder is stored as
a positive demand magnitude in the source export. The maintained mapping
workbook converts it to a negative bunker row and subtracts it from gross LEAP
`Total Primary Supply`. The dashboard consumes those mapped values; it does not
reimplement the sign rule.

The resulting signed identity is:

`TPES = production + imports + exports + international bunkers + stock changes`

Exports and bunkers are normally negative. Stock changes remain outside the
projection-comparable overview supply charts until matching LEAP projections
are available.
