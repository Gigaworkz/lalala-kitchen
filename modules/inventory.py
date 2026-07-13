import streamlit as st
import pandas as pd
from utils.db import fetch_all
from utils.helpers import get_low_stock_items, get_inventory_worth, whatsapp_share_url, correct_market_price, normalize_base_unit

def inventory_page():
    st.markdown("## 📦 Inventory Status — Live Stock Tracker")

    sku_data = fetch_all("sku_master")
    if not sku_data:
        st.warning("SKU Master empty — Supabase la data add pannunga")
        return

    df = pd.DataFrame(sku_data)

    # ── Low Stock Warning Banner ──────────────────────────────────────────────
    low_items = get_low_stock_items()
    if low_items:
        st.error(f"🚨 {len(low_items)} item(s) minimum stock kila irukku — Purchase list check pannunga!")

    # ── Total Inventory Worth ─────────────────────────────────────────────────
    worth = get_inventory_worth()
    st.metric("📦 Total Inventory Worth", f"₹{worth:,.2f}")
    st.divider()

    # ── Live Stock Table ──────────────────────────────────────────────────────
    display_cols = ["Ingerdient Name", "Category", "current_stock", "Min Stock Level",
                    "Purchase unit", "Market Price", "price note"]
    existing_cols = [c for c in display_cols if c in df.columns]
    df_display = df[existing_cols].copy()

    # Color-code low stock
    def highlight_low(row):
        try:
            cur = float(row.get("current_stock", 0))
            mn  = float(row.get("Min Stock Level", 0))
            if cur <= mn:
                return ["background-color: #8B0000; color: white"] * len(row)
        except:
            pass
        return [""] * len(row)

    st.dataframe(
        df_display.style.apply(highlight_low, axis=1),
        use_container_width=True,
        height=400
    )

    st.divider()

    # ── Purchase List Generator (interactive, report-only, no DB writes) ──────
    st.markdown("### 🛒 Generate Purchase List")
    st.caption("Click Generate — low stock items auto-fill aagum. Apparam edit/add/remove ellame idhே report ku mattum, Supabase la edhuvும் change aagathu.")

    if "purchase_list" not in st.session_state:
        st.session_state.purchase_list = {}       # {ingredient_name: qty} — report-only, never saved to DB
    if "purchase_list_active" not in st.session_state:
        st.session_state.purchase_list_active = False

    sku_map_all = {s["Ingerdient Name"]: s for s in sku_data if s.get("Ingerdient Name")}
    all_names   = list(sku_map_all.keys())

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📋 Generate Purchase List", use_container_width=True, type="primary"):
            st.session_state.purchase_list_active = True
            for item in low_items:
                name = item.get("Ingerdient Name")
                if not name:
                    continue
                min_lvl = float(item.get("Min Stock Level", 0) or 0)
                cur     = float(item.get("current_stock", 0) or 0)
                st.session_state.purchase_list[name] = max(min_lvl - cur, 0)
            st.rerun()
    with col_b:
        if st.session_state.purchase_list_active:
            if st.button("🗑️ Clear List", use_container_width=True):
                st.session_state.purchase_list = {}
                st.session_state.purchase_list_active = False
                st.rerun()

    if not st.session_state.purchase_list_active:
        st.info("Generate Purchase List click pannunga — low stock items ah kaatti report start pannalam.")
    else:
        # ➕ Add any item manually — report list ku mattum, DB touch illa
        st.markdown("**➕ Add Item** (report-ku mattum, SKU master la edhuvும் save aagathu)")
        add_col1, add_col2, add_col3 = st.columns([3, 2, 1])
        with add_col1:
            new_item = st.selectbox("Ingredient", ["-- select --"] + all_names, key="pl_add_select")
        add_unit = normalize_base_unit(sku_map_all.get(new_item, {}).get("Purchase unit", "gm")) if new_item != "-- select --" else "gm"
        with add_col2:
            add_qty = st.number_input(f"Qty ({add_unit})", min_value=0.0, step=1.0, key="pl_add_qty")
        with add_col3:
            st.write("")
            if st.button("➕ Add", use_container_width=True, key="pl_add_btn"):
                if new_item != "-- select --":
                    st.session_state.purchase_list[new_item] = add_qty
                    st.rerun()

        st.divider()

        if not st.session_state.purchase_list:
            st.success("✅ Low stock items illa, list empty. Mேலே manual ah add pannalam.")
        else:
            st.markdown("**📝 List — Qty edit pannunga, venaam na ❌ pannunga**")
            total_budget = 0.0
            share_rows = []
            remove_name = None

            for name, qty_val in st.session_state.purchase_list.items():
                sku = sku_map_all.get(name, {})
                base_unit    = normalize_base_unit(sku.get("Purchase unit", "gm"))
                market_price = float(sku.get("Market Price", 0) or 0)
                cur_stock    = sku.get("current_stock", 0)

                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                with c1:
                    st.write(f"**{name}**")
                    st.caption(f"Stock: {cur_stock} {base_unit} · Rate: ₹{market_price:.2f}/{base_unit}")
                with c2:
                    new_qty = st.number_input(f"Qty ({base_unit})", min_value=0.0, step=1.0,
                                               value=float(qty_val), key=f"pl_qty_{name}")
                    st.session_state.purchase_list[name] = new_qty
                with c3:
                    est_price = new_qty * market_price
                    st.metric("Est. ₹", f"{est_price:,.2f}", label_visibility="collapsed")
                with c4:
                    if st.button("❌", key=f"pl_rm_{name}"):
                        remove_name = name

                total_budget += est_price
                share_rows.append((name, new_qty, base_unit, market_price, est_price))

            if remove_name:
                del st.session_state.purchase_list[remove_name]
                st.rerun()

            st.divider()
            st.metric("💰 Estimated Total Budget", f"₹{total_budget:,.2f}")

            # HTML purchase list for download
            rows_html = ""
            for name, qty, unit, rate, est in share_rows:
                rows_html += (f"<tr><td>{name}</td><td>{qty:g} {unit}</td>"
                              f"<td>₹{rate:.2f}/{unit}</td><td>₹{est:.2f}</td></tr>")

            html_list = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'>
<style>body{{font-family:Arial;padding:20px}}h2{{color:#e65c00}}
table{{border-collapse:collapse;width:100%}}th{{background:#e65c00;color:#fff;padding:8px}}
td{{padding:8px;border:1px solid #ddd}}.total{{font-weight:bold;background:#fff3e0}}</style></head><body>
<h2>🛒 LALALA Kitchen — Purchase List</h2>
<p>Generated: {pd.Timestamp.now().strftime('%d-%m-%Y %H:%M')}</p>
<table><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Est. Amount</th></tr>
{rows_html}
<tr class="total"><td colspan="3">Estimated Total Budget</td><td>₹{total_budget:.2f}</td></tr>
</table></body></html>"""

            col1, col2 = st.columns(2)
            with col1:
                st.download_button("🖨️ Download Purchase List", data=html_list,
                                    file_name="purchase_list.html", mime="text/html",
                                    use_container_width=True)
            with col2:
                msg_lines = ["🛒 *LALALA Kitchen Purchase List*", ""]
                for name, qty, unit, rate, est in share_rows:
                    msg_lines.append(f"• {name} — {qty:g}{unit} × ₹{rate:.2f} = ₹{est:.2f}")
                msg_lines.append("")
                msg_lines.append(f"💰 *Estimated Total: ₹{total_budget:,.2f}*")
                msg = "%0A".join(msg_lines)
                wa_url = f"https://wa.me/?text={msg}"
                st.link_button("📲 Share on WhatsApp", wa_url, use_container_width=True)

    st.divider()

    # ── One-Time: Fix Legacy Price Data ───────────────────────────────────────
    with st.expander("🔧 Fix Old Price Data (one-time, per ingredient)"):
        st.caption(
            "Old rows la Market Price 'per 100gm' / 'per kg' madhiri veru convention la "
            "iruntha, idha use panni ஒரே தடவை correct pannunga. Inimela ella purchase "
            "entry um automatic ah 'per 1 base unit' ah than save aagum."
        )
        sku_names_fix = [s["Ingerdient Name"] for s in sku_data if s.get("Ingerdient Name")]
        sku_map_fix   = {s["Ingerdient Name"]: s for s in sku_data}

        item_fix = st.selectbox("🧂 Ingredient", sku_names_fix, key="fix_item")
        if item_fix:
            cur_sku = sku_map_fix.get(item_fix, {})
            base_unit_fix = normalize_base_unit(cur_sku.get("Purchase unit", "gm"))
            st.caption(
                f"Current: Market Price = {cur_sku.get('Market Price', 0)} | "
                f"price note = \"{cur_sku.get('price note', '')}\" | base unit = {base_unit_fix}"
            )

        col1, col2, col3 = st.columns(3)
        with col1:
            ref_amount = st.number_input("Real price ₹ (e.g. 90)", min_value=0.0, step=1.0, key="fix_amount")
        with col2:
            ref_qty = st.number_input("...for this much quantity (e.g. 100)", min_value=0.0, step=1.0, key="fix_qty")
        with col3:
            ref_unit_options = ["gm", "kg", "ml", "litre", "nos"]
            ref_unit = st.selectbox("Unit of that quantity", ref_unit_options, key="fix_unit")

        st.caption("Example: 100gm ku ₹90 na → 90, 100, gm nu podunga")

        if st.button("✅ Correct This Ingredient's Price", key="fix_submit"):
            if item_fix and ref_amount > 0 and ref_qty > 0:
                success, new_price, saved_base_unit = correct_market_price(item_fix, ref_amount, ref_qty, ref_unit)
                if success:
                    st.success(f"✅ {item_fix} — Market Price correct pannachu: ₹{new_price} per 1 {saved_base_unit}")
                    st.rerun()
                else:
                    st.error("⚠️ Correction failed — ingredient not found or invalid quantity")
            else:
                st.warning("⚠️ Ella fields um required")
