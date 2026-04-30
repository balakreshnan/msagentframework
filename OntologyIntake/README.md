# OMS Sample Data (CSV)

Companion sample data for the Order Management System data dictionary (`sample-data-dictionary.docx`) and conceptual model (`sample-data-model.pdf`). All files use UTF-8, comma-separated, with a header row. Foreign keys are referentially valid except where noted under *Intentional anomalies*.

## Files

| File | Rows | Description |
|---|---:|---|
| `customer.csv` | 10 | Natural persons or organizations holding accounts. |
| `account.csv` | 12 | Lifecycle/tier container per customer; some customers hold multiple accounts. |
| `product.csv` | 15 | Catalog items; three are hazmat-flagged. |
| `address.csv` | 15 | Billing and shipping addresses. |
| `payment_method.csv` | 10 | Tokenized payment methods; one default per customer. |
| `order.csv` | 20 | Mix of pending / confirmed / shipped / delivered / cancelled orders across channels. |
| `order_line.csv` | 39 | Line items linked to orders and products. |
| `shipment.csv` | 19 | Carrier-fulfilled shipments incl. one split-fulfillment and one hazmat-compliant carrier. |
| `return.csv` | 5 | Returns against delivered orders within the 30-day window. |

## Foreign-key map

```
customer.customer_id ◀── account.customer_id
customer.customer_id ◀── address.customer_id
customer.customer_id ◀── payment_method.customer_id
customer.customer_id ◀── order.customer_id
order.order_id       ◀── order_line.order_id
product.sku          ◀── order_line.sku
order.order_id       ◀── shipment.order_id
order.order_id       ◀── return.order_id
```

## Controlled vocabularies (for SKOS lifting)

- `customer.segment`: `Bronze | Silver | Gold | Platinum`
- `order.channel`: `web | mobile | pos | marketplace | phone`
- `order.status`: `pending | confirmed | shipped | delivered | cancelled`
- `shipment.status`: `label_created | in_transit | delivered | exception | returned`
- `return.status`: `requested | approved | rejected | completed`
- `return.reason_code`: `DMG | WRG | NDS | CXL | DEF | OTH`
- `address.type`: `billing | shipping`
- `payment_method.type`: `card | wallet | bnpl | bank`

## Intentional anomalies (for validation testing)

These violations are deliberately included so that SHACL / competency-question / business-rule
validators have something to flag during ontology pipeline testing.

| Rule | Description |
|---|---|
| **BR-01 / DQ-01** | Order `70010` has `total_amount = 193.00` but its lines sum to `188.99`. |
| **BR-07 / DQ-04** | Account `2011` has `tier = Gold` while its customer `1009` has `segment = Platinum` (drift). |
| **BR-05** | Order `70018` contains the hazmat product `SKU-BTY-401` and is fulfilled by carrier `UPS-Hazmat` — compliant. Orders `70003` and `70013` also contain hazmat SKUs (`SKU-ELC-103`, `SKU-OUT-301`) and are fulfilled by `DHL`; verify carrier eligibility against your approved hazmat registry downstream. |
| **BR-06** | Customer `1010` has no payment method on file. Customer `1002` has two methods, exactly one default — compliant. |

## Quick load (Python)

```python
import pandas as pd
customer = pd.read_csv('customer.csv')
order    = pd.read_csv('order.csv',    parse_dates=['order_date'])
line     = pd.read_csv('order_line.csv')
# Verify BR-01 across all orders:
line['line_total'] = line.quantity * line.unit_price_at_sale * (1 - line.discount_pct/100)
checked = order.merge(line.groupby('order_id').line_total.sum().reset_index(), on='order_id')
checked['BR_01_drift'] = (checked.total_amount - checked.line_total).round(2)
print(checked.query('BR_01_drift != 0'))
```
