import streamlit as st
import pandas as pd
from utils.db import fetch_all
from utils.helpers import get_low_stock_items, get_inventory_worth, whatsapp_share_url

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

    # ── Purchase List Generator ───────────────────────────────────────────────
    st.markdown("### 🛒 Generate Purchase List")
    if st.button("📋 Generate Purchase List", use_container_width=True):
        if low_items:
            purchase_df = pd.DataFrame(low_items)[["Ingerdient Name", "current_stock",
                                                     "Min Stock Level", "Purchase unit", "Market Price"]]
            purchase_df.columns = ["Item", "Current Stock", "Min Level", "Unit", "Last Price (₹)"]
            st.dataframe(purchase_df, use_container_width=True)

            # HTML purchase list for download/share
            rows_html = ""
            for _, row in purchase_df.iterrows():
                rows_html += f"<tr><td>{row['Item']}</td><td>{row['Current Stock']}</td><td>{row['Min Level']}</td><td>{row['Unit']}</td><td>₹{row['Last Price (₹)']}</td></tr>"

            html_list = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'>
<style>body{{font-family:Arial;padding:20px}}h2{{color:#e65c00}}
table{{border-collapse:collapse;width:100%}}th{{background:#e65c00;color:#fff;padding:8px}}
td{{padding:8px;border:1px solid #ddd}}</style></head><body>
<h2>🛒 LALALA Kitchen — Purchase List</h2>
<p>Generated: {pd.Timestamp.now().strftime('%d-%m-%Y %H:%M')}</p>
<table><tr><th>Item</th><th>Current Stock</th><th>Min Level</th><th>Unit</th><th>Last Price</th></tr>
{rows_html}</table></body></html>"""

            col1, col2 = st.columns(2)
            with col1:
                st.download_button("🖨️ Download Purchase List", data=html_list,
                                   file_name="purchase_list.html", mime="text/html",
                                   use_container_width=True)
            with col2:
                # WhatsApp share as text
                msg_lines = ["🛒 *LALALA Kitchen Purchase List*\n"]
                for _, row in purchase_df.iterrows():
                    msg_lines.append(f"• {row['Item']} (Stock: {row['Current Stock']} {row['Unit']})")
                msg = "%0A".join(msg_lines)
                wa_url = f"https://wa.me/?text={msg}"
                st.link_button("📲 Share on WhatsApp", wa_url, use_container_width=True)
        else:
            st.success("✅ All items are above minimum stock level!")
