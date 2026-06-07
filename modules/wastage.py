import streamlit as st
import pandas as pd
from datetime import date
from utils.db import fetch_all, insert_row, update_row
from utils.helpers import deduct_stock_via_bom, get_bom_cost

def wastage_page():
    st.markdown("## 🗑️ Wastage Entry")

    waste_type = st.radio("Wastage Type", [
        "🧂 Raw Material Loss",
        "🍲 Cooked Item Waste",
        "🎁 Complimentary / Promo"
    ], horizontal=True)

    st.divider()

    # ── Raw Material Loss ─────────────────────────────────────────────────────
    if waste_type == "🧂 Raw Material Loss":
        st.markdown("### 🧂 Raw Material Loss")
        st.caption("SKU stock direct ah correct pannalaam, market price vachu loss calculate aagum")

        sku_data = fetch_all("sku_master")
        sku_names = [s["Ingerdient Name"] for s in sku_data if s.get("Ingerdient Name")]
        sku_map   = {s["Ingerdient Name"]: s for s in sku_data}

        col1, col2 = st.columns(2)
        with col1:
            waste_date = st.date_input("📅 Date", value=date.today(), key="rm_date")
            item_sel   = st.selectbox("🧂 Ingredient", sku_names, key="rm_item")
        with col2:
            waste_qty  = st.number_input("Quantity Lost", min_value=0.0, step=0.1, key="rm_qty")
            waste_unit = st.selectbox("Unit", ["gm", "ml", "kg", "litre", "nos"], key="rm_unit")

        reason = st.text_input("📝 Reason", placeholder="Expired / Spoiled / Spillage", key="rm_reason")

        if item_sel:
            sku = sku_map.get(item_sel, {})
            market_price = float(sku.get("Market Price", 0))
            sku_unit     = sku.get("Purchase unit", "gm")
            # normalize loss qty
            if waste_unit in ["kg", "litre"] and sku_unit in ["gm", "ml"]:
                qty_norm = waste_qty * 1000
            else:
                qty_norm = waste_qty
            # price per base unit
            if sku_unit in ["gm", "ml"]:
                price_per = market_price / 1000
            else:
                price_per = market_price
            loss_value = round(qty_norm * price_per, 2)
            st.info(f"💸 Estimated Loss Value: ₹{loss_value:.2f} (@ ₹{market_price}/{sku_unit})")

        if st.button("✅ Record Raw Material Loss", type="primary", use_container_width=True):
            if waste_qty > 0 and item_sel:
                sku = sku_map.get(item_sel, {})
                current_stock = float(sku.get("current_stock", 0))
                # normalize
                if waste_unit in ["kg", "litre"] and sku.get("Purchase unit","gm") in ["gm","ml"]:
                    qty_norm = waste_qty * 1000
                else:
                    qty_norm = waste_qty
                new_stock = max(0, current_stock - qty_norm)
                update_row("sku_master", "Ingerdient Name", item_sel, {"current_stock": round(new_stock, 3)})
                # Expense entry
                insert_row("accounts", {
                    "date": str(waste_date),
                    "type": "Expense",
                    "category": "Wastage",
                    "item_name": item_sel,
                    "amount": loss_value,
                    "qty": waste_qty,
                    "unit": waste_unit,
                    "notes": f"Raw material loss | {reason or 'No reason given'}"
                })
                st.success(f"✅ {item_sel} — {waste_qty}{waste_unit} loss recorded. Stock updated.")
            else:
                st.warning("⚠️ Quantity enter pannunga")

    # ── Cooked Item Waste ─────────────────────────────────────────────────────
    elif waste_type == "🍲 Cooked Item Waste":
        st.markdown("### 🍲 Cooked Item Waste")
        st.caption("BOM vachu raw material stock deduct aagum, making cost vachu loss calculate aagum")

        menu_data  = fetch_all("menu_master")
        dish_names = [m["Dish Name"] for m in menu_data if m.get("Dish Name")]

        col1, col2 = st.columns(2)
        with col1:
            waste_date = st.date_input("📅 Date", value=date.today(), key="ci_date")
            dish_sel   = st.selectbox("🍲 Dish", dish_names, key="ci_dish")
        with col2:
            waste_qty  = st.number_input("Qty Wasted", min_value=1, step=1, key="ci_qty")
            reason     = st.text_input("📝 Reason", placeholder="Overcooked / Leftover", key="ci_reason")

        if dish_sel:
            making_cost = get_bom_cost(dish_sel)
            total_loss  = making_cost * waste_qty
            st.info(f"💸 Estimated Loss: ₹{total_loss:.2f} ({waste_qty} × ₹{making_cost:.2f} making cost)")

        if st.button("✅ Record Cooked Waste", type="primary", use_container_width=True):
            if dish_sel and waste_qty > 0:
                making_cost = get_bom_cost(dish_sel)
                total_loss  = making_cost * waste_qty
                # Deduct stock via BOM
                errors = deduct_stock_via_bom(dish_sel, waste_qty)
                # Expense
                insert_row("accounts", {
                    "date": str(waste_date),
                    "type": "Expense",
                    "category": "Wastage",
                    "item_name": dish_sel,
                    "amount": round(total_loss, 2),
                    "qty": waste_qty,
                    "unit": "nos",
                    "notes": f"Cooked waste | {reason or 'No reason'}"
                })
                st.success(f"✅ {dish_sel} × {waste_qty} waste recorded. Loss: ₹{total_loss:.2f}")
                if errors:
                    st.warning("⚠️ Stock issues: " + ", ".join(errors))
            else:
                st.warning("⚠️ Dish and quantity select pannunga")

    # ── Complimentary / Promo ─────────────────────────────────────────────────
    elif waste_type == "🎁 Complimentary / Promo":
        st.markdown("### 🎁 Complimentary / Promo")
        st.caption("BOM vachu stock deduct aagum, making cost expense aagum — sale revenue illa")

        menu_data  = fetch_all("menu_master")
        dish_names = [m["Dish Name"] for m in menu_data if m.get("Dish Name")]

        col1, col2 = st.columns(2)
        with col1:
            waste_date   = st.date_input("📅 Date", value=date.today(), key="cp_date")
            dish_sel     = st.selectbox("🍲 Dish", dish_names, key="cp_dish")
        with col2:
            waste_qty    = st.number_input("Qty", min_value=1, step=1, key="cp_qty")
            given_to     = st.text_input("Given To", placeholder="Customer name / Event", key="cp_to")

        if dish_sel:
            making_cost = get_bom_cost(dish_sel)
            total_loss  = making_cost * waste_qty
            st.info(f"💸 Cost: ₹{total_loss:.2f} ({waste_qty} × ₹{making_cost:.2f})")

        if st.button("✅ Record Complimentary", type="primary", use_container_width=True):
            if dish_sel and waste_qty > 0:
                making_cost = get_bom_cost(dish_sel)
                total_loss  = making_cost * waste_qty
                errors = deduct_stock_via_bom(dish_sel, waste_qty)
                insert_row("accounts", {
                    "date": str(waste_date),
                    "type": "Expense",
                    "category": "Complimentary",
                    "item_name": dish_sel,
                    "amount": round(total_loss, 2),
                    "qty": waste_qty,
                    "unit": "nos",
                    "notes": f"Complimentary to: {given_to or 'Unknown'}"
                })
                st.success(f"✅ {dish_sel} × {waste_qty} complimentary recorded. Cost: ₹{total_loss:.2f}")
                if errors:
                    st.warning("⚠️ Stock issues: " + ", ".join(errors))
            else:
                st.warning("⚠️ Dish and quantity select pannunga")

    # ── Wastage History ───────────────────────────────────────────────────────
    st.divider()
    with st.expander("📋 Wastage History"):
        acc_data = fetch_all("accounts")
        waste_records = [a for a in acc_data if a.get("category") in ["Wastage", "Complimentary"]]
        if waste_records:
            df = pd.DataFrame(waste_records)[["date","category","item_name","amount","qty","unit","notes"]]
            df = df.sort_values("date", ascending=False)
            st.dataframe(df, use_container_width=True)
            st.metric("Total Wastage Cost", f"₹{df['amount'].sum():,.2f}")
        else:
            st.info("No wastage records found")
