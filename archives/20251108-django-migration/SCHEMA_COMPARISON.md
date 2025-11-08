# Schema Comparison: `artwork_artwork` (Django) vs `artworks` (Go)

## Overview
This document compares the final schema of the Django `artwork_artwork` table (evolved through 20 migrations) with the Go backend `artworks` table (created in a single migration).

---

## Field-by-Field Comparison

### ✅ Common Fields (Same in Both)

| Field | Django Type | Go Type | Notes |
|-------|-------------|---------|-------|
| `id` | UUID (PK) | UUID (PK) | Both use UUID primary keys |
| `title` | CharField(200) | VARCHAR(255) | Go allows longer titles |
| `painting_number` | IntegerField(null=True) | INTEGER | Both nullable |
| `painting_year` | IntegerField(null=True) | INTEGER | Both nullable |
| `width_inches` | DecimalField(6,4) | DECIMAL(8,4) | Go allows larger values |
| `height_inches` | DecimalField(6,4) | DECIMAL(8,4) | Go allows larger values |
| `price_cents` | IntegerField() | INTEGER | Same |
| `paper` | BooleanField(default=False) | BOOLEAN DEFAULT FALSE | Same |
| `sort_order` | IntegerField(default=0) | INTEGER DEFAULT 0 | Same |
| `created_at` | DateTimeField(auto_now_add) | TIMESTAMP DEFAULT current_timestamp | Same |
| `sold_at` | DateTimeField(null=True) | TIMESTAMP | Both nullable |
| `order_id` | ForeignKey (nullable) | UUID REFERENCES orders (SET NULL) | Both nullable, SET NULL on delete |

---

## 🔴 Key Differences

### 1. **Status Field Type**
- **Django**: `CharField(max_length=20)` with choices constraint
  - Values: `sold`, `available`, `coming_soon`, `not_for_sale`, `unavailable`
- **Go**: `artwork_status` ENUM type
  - Values: `available`, `sold`, `not_for_sale`, `unavailable`, `coming_soon`
  - **Difference**: Go uses database-level ENUM for type safety; Django uses application-level validation

### 2. **Medium Field**
- **Django**: `CharField(max_length=20)` with choices constraint
  - Values: `oil_panel`, `acrylic_panel`, `oil_mdf`, `oil_paper`, `unknown`
- **Go**: `artwork_medium` ENUM type
  - Values: `oil_panel`, `acrylic_panel`, `oil_mdf`, `oil_paper`, `unknown`
  - **Difference**: Same values, but Go uses database-level ENUM

### 3. **Category Field**
- **Django**: `CharField(max_length=20)` with choices constraint
  - Values: `figure`, `landscape`, `multi_figure`, `other`
- **Go**: `artwork_category` ENUM type
  - Values: `figure`, `landscape`, `multi_figure`, `other`
  - **Difference**: Same values, but Go uses database-level ENUM

### 4. **Shipment Field**
- **Django**: `ForeignKey` to `orders.Shipment` (nullable, SET_NULL on delete)
- **Go**: **NOT PRESENT** - No shipment field in the Go schema
  - **Impact**: Django tracks which shipment an artwork belongs to; Go does not

### 5. **Title Length**
- **Django**: `max_length=200`
- **Go**: `VARCHAR(255)`
  - **Difference**: Go allows longer titles (255 vs 200 characters)

### 6. **Decimal Precision**
- **Django**: `max_digits=6, decimal_places=4` (allows values up to 99.9999)
- **Go**: `DECIMAL(8,4)` (allows values up to 9999.9999)
  - **Difference**: Go allows much larger dimensions

---

## 📊 Summary Table

| Aspect | Django `artwork_artwork` | Go `artworks` |
|--------|-------------------------|---------------|
| **Total Fields** | 15 fields | 14 fields |
| **Status Type** | CharField | ENUM |
| **Medium Type** | CharField | ENUM |
| **Category Type** | CharField | ENUM |
| **Shipment Field** | ✅ Present | ❌ Missing |
| **Title Max Length** | 200 chars | 255 chars |
| **Dimension Max** | 99.9999 | 9999.9999 |
| **Constraints** | Application-level | Database-level ENUMs |

---

## 🔍 Migration History Summary (Django)

The Django `artwork_artwork` table evolved through these key changes:
1. **0001**: Initial table with `id`, `title`, `size`, `price_cents`, `status`, `creation_date`
2. **0002**: Added `order` (IntegerField)
3. **0005-0007**: Converted `order` to ForeignKey, changed delete behavior
4. **0008**: Added `sort_order`
5. **0009**: Renamed `creation_date` → `created_at`
6. **0014**: Added `shipment` ForeignKey
7. **0015**: Updated status choices (added "unavailable")
8. **0017**: Moved `order` FK to `orders.Order`, `shipment` FK to `orders.Shipment`
9. **0018**: Removed `size`, added `category`, `medium`, `painting_number`, `painting_year`, `paper`, `width_inches`, `height_inches`
10. **0019**: Added `sold_at`
11. **0020**: Updated status choices (added "not_for_sale")

---

## ⚠️ Potential Issues & Recommendations

### 1. **Missing Shipment Field**
The Go schema lacks the `shipment` field that exists in Django. If shipment tracking is needed in the Go backend, this field should be added.

### 2. **Status Value Order**
The ENUM definitions have different ordering:
- Django: `sold`, `available`, `coming_soon`, `not_for_sale`, `unavailable`
- Go: `available`, `sold`, `not_for_sale`, `unavailable`, `coming_soon`
- **Impact**: This shouldn't affect functionality, but could cause confusion

### 3. **Type Safety**
- Go's ENUM types provide database-level constraints (better data integrity)
- Django's CharField relies on application-level validation (more flexible but less strict)

### 4. **Data Migration Considerations**
When migrating data from Django to Go:
- Ensure status/medium/category values match exactly
- Handle artworks with `shipment` references (may need separate shipment tracking)
- Verify dimension values fit within Go's larger DECIMAL range
- Title truncation may be needed if any exceed 200 chars (though Go allows 255)

---

## 📝 Recommendations

1. **Add shipment field to Go schema** if shipment tracking is required
2. **Standardize ENUM value ordering** for consistency
3. **Consider adding database-level constraints** in Django (using CheckConstraint) for better parity
4. **Document any business logic differences** between the two implementations

