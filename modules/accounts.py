import streamlit as st
import pandas as pd
from datetime import date, timedelta
from utils.db import fetch_all, insert_row, update_row
from utils.helpers import add_stock_purchase, normalize_base_unit, get_purchase_unit_options, convert_to_base_qty

def accounts_page():
    st.markdown("## 💰 Accounts Entry Panel")

    tab = st.radio("Select Entry Type", [
        "📦 Purchase Entry",
        "🏢 Fixed Expenses",
        "💳 Pending Credit Dashboard",
        "📱 Channel Payout Settlements"
    ], horizontal=True)

    st.divider()

    # ── Purchase Entry ────────────────────────────────────────────────────────
    if tab == "📦 Purchase Entry":
        st.markdown("### 📦 Purchase Entry")
        st.caption("Raw material vanginal — stock add aagum, market price update aagum, expense record aagum")

        sku_data = fetch_all("sku_master")
        sku_names = [s["Ingerdient Name"] for s in sku_data if s.get("Ingerdient Name")]
        sku_map   = {s["Ingerdient Name"]: s for s in sku_data}

        col1, col2 = st.columns(2)
        with col1:
            purchase_date = st.date_input("📅 Purchase Date", value=date.today(), key="pur_date")
            item_selected = st.selectbox("🧂 Select Ingredient", sku_names, key="pur_item")

        # Base unit is fixed per ingredient (gm/ml/nos) — user can only pick a
        # convenience unit that converts cleanly into it (e.g. kg for a gm item,
        # litre for an ml item). No mismatched unit can ever be selected.
        base_unit    = normalize_base_unit(sku_map.get(item_selected, {}).get("Purchase unit", "gm")) if item_selected else "gm"
        unit_options = get_purchase_unit_options(base_unit)

        with col2:
            qty_purchased = st.number_input("Quantity", min_value=0.0, step=0.1, key="pur_qty")
            unit_selected = st.selectbox("Unit", unit_options, key="pur_unit")

        st.caption(f"📦 Stock tracked in base unit: **{base_unit}** for this ingredient")

        total_amount = st.number_input("💰 Total Amount Paid (₹)", min_value=0.0, step=1.0, key="pur_price",
                                        help="Total bill amount for this purchase (e.g. 5 litre Oil vanginal total ₹795 nu kudunga)")

        qty_base_preview = 0
        if qty_purchased > 0 and total_amount > 0:
            qty_base_preview = convert_to_base_qty(qty_purchased, unit_selected, base_unit)
            rate_preview = total_amount / qty_base_preview if qty_base_preview else 0
            st.caption(f"≈ {qty_base_preview:.0f} {base_unit} stock add aagum · ₹{rate_preview:.3f} per {base_unit}")

        notes_pur = st.text_input("📝 Notes (optional)", key="pur_notes")

        if st.button("✅ Submit Purchase", type="primary", use_container_width=True):
            if item_selected and qty_purchased > 0 and total_amount >= 0:
                success, qty_base, saved_base_unit = add_stock_purchase(
                    item_selected, qty_purchased, unit_selected, total_amount
                )
                if success:
                    # Ledger entry logged in base unit too — kg/litre never
                    # appear anywhere in stored data, only in the UI at entry time.
                    insert_row("accounts", {
                        "date": str(purchase_date),
                        "type": "Expense",
                        "category": "Purchase",
                        "item_name": item_selected,
                        "amount": round(total_amount, 2),
                        "qty": round(qty_base, 3),
                        "unit": saved_base_unit,
                        "notes": notes_pur or f"Purchase: {qty_purchased}{unit_selected} ({qty_base:.0f}{saved_base_unit}) for total ₹{total_amount}"
                    })
                    st.success(f"✅ {item_selected} — {qty_purchased}{unit_selected} = {qty_base:.0f}{saved_base_unit} added to stock. Expense ₹{total_amount:.2f} recorded.")
                else:
                    st.error("⚠️ Stock update failed — ingredient not found or invalid quantity")
            else:
                st.warning("⚠️ All fields required")

    # ── Fixed Expenses ────────────────────────────────────────────────────────
    elif tab == "🏢 Fixed Expenses":
        st.markdown("### 🏢 Fixed Expenses")
        col1, col2 = st.columns(2)
        with col1:
            exp_date = st.date_input("📅 Date", value=date.today(), key="fix_date")
            exp_cat  = st.selectbox("Category", ["Rent", "EB Bill", "Salary", "Transport", "Gas Bill",
                                                  "Water Bill", "Wifi Bill", "Advertisement", "Maintenance",
                                                  "Other"], key="fix_cat")
        with col2:
            exp_amount = st.number_input("Amount (₹)", min_value=0.0, step=10.0, key="fix_amt")
            exp_notes  = st.text_input("📝 Notes", key="fix_notes")

        if st.button("💾 Save Expense", type="primary", use_container_width=True):
            if exp_amount > 0:
                insert_row("accounts", {
                    "date": str(exp_date),
                    "type": "Expense",
                    "category": exp_cat,
                    "item_name": exp_cat,
                    "amount": exp_amount,
                    "qty": 1,
                    "unit": "fixed",
                    "notes": exp_notes
                })
                st.success(f"✅ ₹{exp_amount:.0f} — {exp_cat} expense saved!")
            else:
                st.warning("⚠️ Amount enter pannunga")

        # Show recent fixed expenses
        st.divider()
        st.markdown("#### Recent Fixed Expenses")
        acc_data = fetch_all("accounts")
        fixed_exp = [a for a in acc_data if a.get("category") in
                     ["Rent","EB Bill","Salary","Transport","Gas Bill","Water Bill","Wifi Bill","Advertisement","Maintenance","Other"]]
        if fixed_exp:
            st.dataframe(pd.DataFrame(fixed_exp)[["date","category","amount","notes"]].sort_values("date", ascending=False).head(20),
                         use_container_width=True)

    # ── Pending Credit Dashboard ──────────────────────────────────────────────
    elif tab == "💳 Pending Credit Dashboard":
        st.markdown("### 💳 Pending Credit Dashboard")

        orders = fetch_all("orders")
        acc_data = fetch_all("accounts")

        credit_orders = [o for o in orders if o.get("payment_mode") == "Credit"]

        # Calculate recovered amounts per bill
        recovered_map = {}
        for a in acc_data:
            if a.get("category") == "Credit Recovery":
                bill = a.get("notes", "")
                recovered_map[bill] = recovered_map.get(bill, 0) + float(a.get("amount", 0))

        pending = []
        for o in credit_orders:
            total_amt = float(o.get("amount", 0))
            recovered = recovered_map.get(o.get("bill_number", ""), 0)
            balance   = total_amt - recovered
            if balance > 0:
                pending.append({
                    "Bill No": o.get("bill_number"),
                    "Date": o.get("date"),
                    "Customer": o.get("customer_name"),
                    "Phone": o.get("phone_number"),
                    "Platform": o.get("platform"),
                    "Total (₹)": total_amt,
                    "Recovered (₹)": recovered,
                    "Balance (₹)": round(balance, 2)
                })

        if pending:
            pending_df = pd.DataFrame(pending)
            total_pending = pending_df["Balance (₹)"].sum()
            st.metric("💸 Total Pending Credit", f"₹{total_pending:,.2f}")
            st.dataframe(pending_df, use_container_width=True)
        else:
            st.success("✅ No pending credits!")

        st.divider()
        st.markdown("#### 💰 Record Credit Recovery")
        col1, col2 = st.columns(2)
        with col1:
            rec_date = st.date_input("📅 Date", value=date.today(), key="rec_date")
            client_options = list(set([p["Bill No"] for p in pending])) if pending else []
            sel_bill = st.selectbox("Select Bill", client_options if client_options else ["No pending credits"], key="rec_bill")
        with col2:
            rec_amount = st.number_input("Amount Recovered (₹)", min_value=0.0, step=10.0, key="rec_amt")

        if st.button("✅ Submit Recovery", type="primary", use_container_width=True):
            if rec_amount > 0 and sel_bill and sel_bill != "No pending credits":
                insert_row("accounts", {
                    "date": str(rec_date),
                    "type": "Revenue",
                    "category": "Credit Recovery",
                    "item_name": "Credit Recovery",
                    "amount": rec_amount,
                    "qty": 1,
                    "unit": "bill",
                    "notes": sel_bill
                })
                st.success(f"✅ ₹{rec_amount:.0f} recovery recorded for {sel_bill}!")
                st.rerun()

    # ── Channel Payout Settlements ────────────────────────────────────────────
    elif tab == "📱 Channel Payout Settlements":
        st.markdown("### 📱 Platform Payout Settlement")
        st.caption("Swiggy/Zomato settlement Wednesday select pannunga — sale window automatic aa calculate aagum")

        col1, col2 = st.columns(2)
        with col1:
            platform_sel = st.selectbox("Platform", ["Swiggy", "Zomato"], key="pay_platform")
        with col2:
            settlement_date = st.date_input("📅 Settlement Date (Wednesday)", value=date.today(), key="pay_settle_date")

        if settlement_date.weekday() != 2:  # Monday=0 ... Wednesday=2
            st.warning("⚠️ Settlement date Wednesday ah select pannunga (Swiggy/Zomato Wednesday than settle pannuvanga)")

        # ── Auto-calculate sale window based on platform pattern ─────────────────
        if platform_sel == "Swiggy":
            # Sun-Sat sales -> next Wednesday settlement (4 days after Saturday)
            from_date = settlement_date - timedelta(days=10)  # Sunday
            to_date   = settlement_date - timedelta(days=4)   # Saturday
        else:  # Zomato
            # Mon-Sun sales -> next Wednesday settlement (3 days after Sunday)
            from_date = settlement_date - timedelta(days=9)   # Monday
            to_date   = settlement_date - timedelta(days=3)   # Sunday

        st.info(f"🗓️ Sale Window: **{from_date.strftime('%d-%b (%a)')} → {to_date.strftime('%d-%b (%a)')}** "
                f"({(to_date - from_date).days + 1} days) → Settlement on **{settlement_date.strftime('%d-%b (%a)')}**")

        orders = fetch_all("orders")
        filtered = [o for o in orders if
                    o.get("platform") == platform_sel and
                    str(from_date) <= str(o.get("date", "")) <= str(to_date)]

        total_order_value = sum(float(o.get("amount", 0)) for o in filtered)
        num_orders = len(filtered)

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric(f"📦 {platform_sel} Orders", num_orders)
            st.metric("💰 Total Order Value", f"₹{total_order_value:,.2f}")
        with col_b:
            bank_payout = st.number_input("🏦 Actual Bank Payout Received (₹)", min_value=0.0, step=10.0, key="bank_payout")

        if bank_payout > 0:
            commission = total_order_value - bank_payout
            comm_pct   = (commission / total_order_value * 100) if total_order_value > 0 else 0
            st.metric("💸 Platform Commission", f"₹{commission:,.2f}", delta=f"-{comm_pct:.1f}%")

            if st.button(f"✅ Record {platform_sel} Payout Settlement", type="primary", use_container_width=True):
                # Revenue entry
                insert_row("accounts", {
                    "date": str(settlement_date),
                    "type": "Revenue",
                    "category": f"{platform_sel} Payout",
                    "item_name": f"{platform_sel} Settlement",
                    "amount": bank_payout,
                    "qty": num_orders,
                    "unit": "orders",
                    "notes": f"Sales {from_date} to {to_date} | Orders: ₹{total_order_value:.2f} | Commission: ₹{commission:.2f} ({comm_pct:.1f}%)"
                })
                # Commission expense entry
                insert_row("accounts", {
                    "date": str(settlement_date),
                    "type": "Expense",
                    "category": "Platform Commission",
                    "item_name": f"{platform_sel} Commission",
                    "amount": commission,
                    "qty": num_orders,
                    "unit": "orders",
                    "notes": f"Sales {from_date} to {to_date} | {comm_pct:.1f}% commission"
                })
                st.success(f"✅ {platform_sel} settlement recorded! Revenue: ₹{bank_payout:.2f}, Commission: ₹{commission:.2f}")

        # Outstanding display
        st.divider()
        st.markdown(f"#### 🔴 {platform_sel} Outstanding (Unsettled Orders)")
        acc_data = fetch_all("accounts")
        settled_amounts = sum(float(a.get("amount",0)) for a in acc_data
                              if a.get("category") == f"{platform_sel} Payout")
        all_platform_orders = [o for o in orders if o.get("platform") == platform_sel]
        all_platform_total  = sum(float(o.get("amount",0)) for o in all_platform_orders)
        outstanding = max(0, all_platform_total - settled_amounts)
        st.metric(f"💸 {platform_sel} Outstanding", f"₹{outstanding:,.2f}")
