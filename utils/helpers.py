import streamlit as st
import pandas as pd
from datetime import date, datetime
from utils.db import fetch_all, fetch_where, insert_row, update_row, get_supabase

# ── Bill Number Generator ──────────────────────────────────────────────────────
def generate_bill_number():
    orders = fetch_all("orders", order_col="id")
    year = datetime.now().year
    if not orders:
        return f"LALALA-{year}-001"
    last_bills = [o.get("bill_number", "") for o in orders if o.get("bill_number", "").startswith(f"LALALA-{year}-")]
    if not last_bills:
        return f"LALALA-{year}-001"
    nums = []
    for b in last_bills:
        try:
            nums.append(int(b.split("-")[-1]))
        except:
            pass
    next_num = max(nums) + 1 if nums else 1
    return f"LALALA-{year}-{str(next_num).zfill(3)}"

# ── Customer Autofill ──────────────────────────────────────────────────────────
def get_customer_by_phone(phone: str):
    if not phone or len(phone) != 10:
        return None
    orders = fetch_all("orders")
    for o in orders:
        if str(o.get("phone_number", "")) == phone:
            return o.get("customer_name", "")
    return None

def get_phone_by_name(name: str):
    if not name:
        return None
    orders = fetch_all("orders")
    name_lower = name.strip().lower()
    for o in orders:
        if str(o.get("customer_name", "")).strip().lower() == name_lower:
            ph = o.get("phone_number", "")
            if ph and ph != "N/A":
                return ph
    return None

# ── Base Unit Helpers ───────────────────────────────────────────────────────────
# current_stock and Market Price are ALWAYS stored in a base unit: gm, ml, or nos.
# kg / litre are purchase-time convenience units only — they get converted to
# base unit immediately and are never stored anywhere in SKU/BOM/stock logic.
BASE_UNITS = ("gm", "ml", "nos")

def normalize_base_unit(unit: str) -> str:
    """Map any unit (including legacy kg/litre saved in old rows) to its
    correct base unit — gm, ml, or nos. Self-heals old SKU data over time."""
    u = (unit or "gm").strip().lower()
    if u in ("kg", "gm"):
        return "gm"
    if u in ("litre", "liter", "l", "ml"):
        return "ml"
    return "nos"

def get_purchase_unit_options(base_unit: str):
    """Units the Purchase Entry UI should offer for a given ingredient,
    based on its base unit. No free unit choice — only conversions that
    make sense for that base unit are shown."""
    base_unit = normalize_base_unit(base_unit)
    if base_unit == "gm":
        return ["gm", "kg"]
    if base_unit == "ml":
        return ["ml", "litre"]
    return ["nos"]

def convert_to_base_qty(qty: float, entry_unit: str, base_unit: str) -> float:
    """Convert a quantity entered in entry_unit (gm/kg/ml/litre/nos) into the
    ingredient's base unit (gm/ml/nos). This is the single place unit
    conversion happens — every other function should call this instead of
    re-implementing kg/litre math."""
    base_unit = normalize_base_unit(base_unit)
    entry_unit = (entry_unit or base_unit).strip().lower()
    if base_unit == "nos":
        return qty
    if base_unit == "gm":
        return qty * 1000 if entry_unit == "kg" else qty
    if base_unit == "ml":
        return qty * 1000 if entry_unit == "litre" else qty
    return qty

# ── BOM Cost Calculator ────────────────────────────────────────────────────────
def get_bom_cost(dish_name: str):
    bom_data = fetch_where("bom_master", "Dish Name", dish_name)
    sku_data = fetch_all("sku_master")
    sku_price_map = {s["Ingerdient Name"]: float(s.get("Market Price", 0) or 0) for s in sku_data}
    sku_base_map  = {s["Ingerdient Name"]: normalize_base_unit(s.get("Purchase unit", "gm")) for s in sku_data}
    total_cost = 0.0
    for item in bom_data:
        ingredient = item.get("Ingerdient Name", "")
        req_qty    = float(item.get("Required quantity", 0))
        unit       = item.get("Unit", "gm")
        base_unit  = sku_base_map.get(ingredient, "gm")
        # Market Price is always per base unit already — no /1000 needed
        price_per_base_unit = sku_price_map.get(ingredient, 0)
        qty_in_base = convert_to_base_qty(req_qty, unit, base_unit)
        total_cost += price_per_base_unit * qty_in_base
    return round(total_cost, 2)

# ── Stock Deduction via BOM ────────────────────────────────────────────────────
def deduct_stock_via_bom(dish_name: str, ordered_qty: float, reason: str = "sale"):
    bom_data = fetch_where("bom_master", "Dish Name", dish_name)
    sku_data = fetch_all("sku_master")
    sku_map  = {s["Ingerdient Name"]: s for s in sku_data}
    errors   = []
    for item in bom_data:
        ingredient = item.get("Ingerdient Name", "")
        req_qty    = float(item.get("Required quantity", 0)) * ordered_qty
        unit       = item.get("Unit", "gm")
        sku = sku_map.get(ingredient)
        if not sku:
            errors.append(f"{ingredient} — SKU not found")
            continue
        base_unit = normalize_base_unit(sku.get("Purchase unit", "gm"))
        current = float(sku.get("current_stock", 0) or 0)
        req_qty_base = convert_to_base_qty(req_qty, unit, base_unit)
        new_stock = max(0, current - req_qty_base)
        update_row("sku_master", "Ingerdient Name", ingredient, {"current_stock": round(new_stock, 3)})
    return errors

# ── Add Stock (Purchase) ───────────────────────────────────────────────────────
def add_stock_purchase(ingredient: str, qty: float, unit: str, total_amount: float):
    """qty/unit = whatever the user entered at purchase time (gm/kg/ml/litre/nos).
    total_amount = total ₹ paid for that purchase.
    Converts qty to the ingredient's base unit (gm/ml/nos), adds it to
    current_stock, and stores Market Price as ₹ per base unit.
    Returns (success, qty_in_base_unit, base_unit)."""
    sku_data = fetch_where("sku_master", "Ingerdient Name", ingredient)
    if not sku_data:
        return False, 0, ""
    sku = sku_data[0]
    base_unit = normalize_base_unit(sku.get("Purchase unit", "gm"))
    current = float(sku.get("current_stock", 0) or 0)

    qty_base = convert_to_base_qty(qty, unit, base_unit)
    if qty_base <= 0:
        return False, 0, base_unit

    price_per_base_unit = total_amount / qty_base
    new_stock = current + qty_base

    update_row("sku_master", "Ingerdient Name", ingredient, {
        "current_stock": round(new_stock, 3),
        "Market Price": round(price_per_base_unit, 4),
        "Purchase unit": base_unit,  # self-heals any legacy kg/litre value
        "price note": f"per 1 {base_unit}",  # removes ambiguity — always per 1 base unit now
    })
    return True, qty_base, base_unit

# ── One-Time Legacy Price Correction ───────────────────────────────────────────
def correct_market_price(ingredient: str, reference_amount: float, reference_qty: float, reference_unit: str):
    """For SKU rows whose Market Price was entered under an old convention
    (e.g. '₹90 for 100 gm', reflected only in the free-text price note),
    this recalculates the correct per-base-unit price from a known real-world
    reference and fixes both Market Price and price note in one shot.

    Example: reference_amount=90, reference_qty=100, reference_unit='gm'
    (i.e. "₹90 per 100 gm") on an ingredient whose base unit is gm →
    stores Market Price = 0.9 (₹ per 1 gm), price note = 'per 1 gm'."""
    sku_data = fetch_where("sku_master", "Ingerdient Name", ingredient)
    if not sku_data:
        return False, 0, ""
    sku = sku_data[0]
    base_unit = normalize_base_unit(sku.get("Purchase unit", "gm"))
    qty_base = convert_to_base_qty(reference_qty, reference_unit, base_unit)
    if qty_base <= 0:
        return False, 0, base_unit

    price_per_base_unit = reference_amount / qty_base
    update_row("sku_master", "Ingerdient Name", ingredient, {
        "Market Price": round(price_per_base_unit, 4),
        "Purchase unit": base_unit,
        "price note": f"per 1 {base_unit}",
    })
    return True, round(price_per_base_unit, 4), base_unit

# ── Low Stock Items ────────────────────────────────────────────────────────────
def get_low_stock_items():
    sku_data = fetch_all("sku_master")
    low = []
    for s in sku_data:
        cur = float(s.get("current_stock", 0))
        mn = float(s.get("Min Stock Level") or 0)
        if cur <= mn:
            low.append(s)
    return low

def get_inventory_worth():
    """current_stock and Market Price are both always per base unit
    (gm/ml/nos), so this is a plain multiplication — no /1000 conversion
    needed anywhere."""
    sku_data = fetch_all("sku_master")
    total = 0.0
    for s in sku_data:
        cur = float(s.get("current_stock") or 0)
        price = float(s.get("Market Price", 0) or 0)
        total += cur * price
    return round(total, 2)

# ── Bill HTML Generator ────────────────────────────────────────────────────────
def generate_bill_html(bill_data: dict, cart_items: list) -> str:
    rows = ""
    subtotal = 0
    for i, item in enumerate(cart_items, 1):
        amt = item["qty"] * item["price"]
        subtotal += amt
        rows += f"""<tr>
          <td style='padding:6px 8px;border-bottom:1px solid #eee'>{i}</td>
          <td style='padding:6px 8px;border-bottom:1px solid #eee'>{item['dish']}</td>
          <td style='padding:6px 8px;border-bottom:1px solid #eee;text-align:center'>{item['qty']}</td>
          <td style='padding:6px 8px;border-bottom:1px solid #eee;text-align:right'>₹{item['price']:.0f}</td>
          <td style='padding:6px 8px;border-bottom:1px solid #eee;text-align:right'>₹{amt:.0f}</td>
        </tr>"""
    html = f"""<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<style>
  body{{font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:20px;color:#222}}
  h2{{text-align:center;color:#e65c00;margin:0}}
  .sub{{text-align:center;color:#888;font-size:12px;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#e65c00;color:#fff;padding:8px;text-align:left}}
  .total{{font-size:16px;font-weight:bold;text-align:right;padding:10px 8px}}
  .footer{{text-align:center;margin-top:20px;font-size:11px;color:#aaa}}
  .info{{font-size:12px;margin-bottom:12px;line-height:1.8}}
</style></head><body>
<h2>🍽️ LALALA Cloud Kitchen</h2>
<div class='sub'>Signature Kitchen</div>
<hr/>
<div class='info'>
  <b>Bill No:</b> {bill_data.get('bill_number','')}<br/>
  <b>Date:</b> {bill_data.get('date','')}<br/>
  <b>Customer:</b> {bill_data.get('customer_name','')}<br/>
  <b>Phone:</b> {bill_data.get('phone_number','')}<br/>
  <b>Platform:</b> {bill_data.get('platform','')}<br/>
  <b>Payment:</b> {bill_data.get('payment_mode','')}
</div>
<table>
  <tr><th>#</th><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th></tr>
  {rows}
  <tr><td colspan='4' class='total'>Total</td><td class='total'>₹{subtotal:.0f}</td></tr>
</table>
<div class='footer'>Thank you for your order! 🙏<br/>LALALA Cloud Kitchen</div>
</body></html>"""
    return html

def whatsapp_share_url(phone: str, bill_number: str, amount: float) -> str:
    if not phone or phone == "N/A":
        return ""
    clean_phone = "91" + phone.strip()
    msg = f"Hi! Your order at LALALA Cloud Kitchen is confirmed 🍽️%0ABill No: {bill_number}%0AAmount: ₹{amount:.0f}%0AThank you!"
    return f"https://wa.me/{clean_phone}?text={msg}"
