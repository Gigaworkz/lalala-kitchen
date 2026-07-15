import streamlit as st
import pandas as pd
from datetime import date
from utils.db import fetch_all, insert_row
from utils.helpers import (
    generate_bill_number, get_customer_by_phone, get_phone_by_name,
    deduct_stock_via_bom, generate_bill_html, whatsapp_share_url
)

def billing_page():
    st.markdown("## 🧾 Billing Counter")

    # ── Auto Bill Number ──────────────────────────────────────────────────────
    if "bill_number" not in st.session_state:
        st.session_state.bill_number = generate_bill_number()
    if "cart" not in st.session_state:
        st.session_state.cart = []

    st.markdown(f"### 📋 Bill No: `{st.session_state.bill_number}`")
    st.divider()

    # ── Section 1: Customer Details ───────────────────────────────────────────
    st.markdown("#### 1. Customer Details")
    col1, col2 = st.columns(2)

    with col1:
        phone_input = st.text_input("📱 Phone Number", max_chars=10, key="phone_input",
                                     placeholder="10 digit / N/A")
        phone_val = phone_input.strip()
        if phone_val and phone_val != "N/A":
            if len(phone_val) != 10 or not phone_val.isdigit():
                st.warning("⚠️ Phone number must be exactly 10 digits")
            else:
                matched_name = get_customer_by_phone(phone_val)
                if matched_name and not st.session_state.get("name_manual"):
                    st.session_state["autofill_name"] = matched_name

    with col2:
        autofill_name = st.session_state.get("autofill_name", "")
        name_input = st.text_input("👤 Customer Name", value=autofill_name, key="name_input")
        if name_input and not st.session_state.get("autofill_name"):
            matched_phone = get_phone_by_name(name_input)
            if matched_phone and (not phone_val or phone_val == "N/A"):
                st.session_state["autofill_phone"] = matched_phone
                st.info(f"📱 Phone autofilled: {matched_phone}")

    col3, col4, col5 = st.columns(3)
    with col3:
        bill_date = st.date_input("📅 Bill Date", value=date.today())
    with col4:
        platform = st.selectbox("🚀 Platform", ["Takeaway", "Swiggy", "Zomato", "Party Order"])
    with col5:
        if platform in ["Swiggy", "Zomato"]:
            payment_mode = "Credit"
            st.selectbox("💳 Payment Mode", ["Credit"], disabled=True)
        else:
            payment_mode = st.selectbox("💳 Payment Mode", ["Cash", "UPI", "Credit"])

    st.divider()

    # ── Section 2: Add Dishes ─────────────────────────────────────────────────
    st.markdown("#### 2. Add Dishes")
    menu_data = fetch_all("menu_master")
    dish_names = [m["Dish Name"] for m in menu_data if m.get("Dish Name")]
    price_map  = {m["Dish Name"]: float(m.get("Price", 0)) for m in menu_data}

    col_a, col_b, col_c = st.columns([3, 1, 1])
    with col_a:
        selected_dish = st.selectbox("🍲 Search Dish", ["-- Select --"] + dish_names)
    with col_b:
        qty = st.number_input("Qty", min_value=1, max_value=50, value=1, step=1)
    with col_c:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Add to Cart", use_container_width=True):
            if selected_dish != "-- Select --":
                price = price_map.get(selected_dish, 0)
                # check if already in cart
                found = False
                for item in st.session_state.cart:
                    if item["dish"] == selected_dish:
                        item["qty"] += qty
                        found = True
                        break
                if not found:
                    st.session_state.cart.append({
                        "dish": selected_dish, "qty": qty, "price": price
                    })
                st.success(f"✅ Added: {selected_dish} × {qty}")

    st.divider()

    # ── Section 3: Invoice View ───────────────────────────────────────────────
    st.markdown("#### 3. Invoice")
    if st.session_state.cart:
        total = 0
        for i, item in enumerate(st.session_state.cart):
            amt = item["qty"] * item["price"]
            total += amt
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 0.6])
            with c1: st.write(f"**{item['dish']}**")
            with c2: st.write(f"× {item['qty']}")
            with c3: st.write(f"₹{item['price']:.0f}")
            with c4: st.write(f"₹{amt:.0f}")
            with c5:
                if st.button("🗑️", key=f"remove_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()

        st.markdown(f"### 💰 Subtotal: ₹{total:.0f}")
        discount = st.number_input("🏷️ Discount (₹)", min_value=0.0, max_value=float(total),
                                    value=0.0, step=1.0, key="discount_input")
        net_total = total - discount
        if discount > 0:
            st.markdown(f"**Discount: −₹{discount:.0f}**")
            st.markdown(f"### 💰 Net Total: ₹{net_total:.0f}")

        st.divider()

        # ── Section 4: Checkout ───────────────────────────────────────────────
        st.markdown("#### 4. Generate Bill")
        if st.button("🧾 Generate Bill", type="primary", use_container_width=True):
            phone_final = phone_val if phone_val else "N/A"
            name_final  = name_input.strip() if name_input.strip() else "Walk-in"
            items_summary = ", ".join([f"{i['dish']}×{i['qty']}" for i in st.session_state.cart])

            # 1. Save to orders table
            order_data = {
                "date": str(bill_date),
                "bill_number": st.session_state.bill_number,
                "customer_name": name_final,
                "phone_number": phone_final,
                "platform": platform,
                "payment_mode": payment_mode,
                "amount": net_total,
                "items_summary": items_summary
            }
            insert_row("orders", order_data)

            # 2. Accounts entry (non-credit)
            if payment_mode != "Credit":
                insert_row("accounts", {
                    "date": str(bill_date),
                    "type": "Revenue",
                    "category": "Sales",
                    "item_name": f"Bill {st.session_state.bill_number}",
                    "amount": net_total,
                    "qty": 1,
                    "unit": "bill",
                    "notes": f"{platform} | {payment_mode} | {items_summary}"
                })

            # 2b. Discount logged separately so it can be tracked in P&L
            if discount > 0:
                insert_row("accounts", {
                    "date": str(bill_date),
                    "type": "Expense",
                    "category": "Discount",
                    "item_name": f"Bill {st.session_state.bill_number}",
                    "amount": discount,
                    "qty": 1,
                    "unit": "bill",
                    "notes": f"Discount on {platform} bill | {items_summary}"
                })

            # 3. Deduct stock via BOM
            deduct_errors = []
            for item in st.session_state.cart:
                errs = deduct_stock_via_bom(item["dish"], item["qty"])
                deduct_errors.extend(errs)

            st.success(f"✅ Bill {st.session_state.bill_number} saved successfully!")
            if deduct_errors:
                st.warning("⚠️ Stock deduction issues: " + ", ".join(deduct_errors))

            # 4. Bill HTML + WhatsApp
            bill_info = {
                "bill_number": st.session_state.bill_number,
                "date": str(bill_date),
                "customer_name": name_final,
                "phone_number": phone_final,
                "platform": platform,
                "payment_mode": payment_mode
            }
            # Add a negative "Discount" line so the printed bill's total nets out correctly
            # without needing to touch the shared generate_bill_html helper.
            cart_for_bill = list(st.session_state.cart)
            if discount > 0:
                cart_for_bill.append({"dish": "Discount", "qty": 1, "price": -discount})
            html_bill = generate_bill_html(bill_info, cart_for_bill)

            col_p, col_w = st.columns(2)
            with col_p:
                st.download_button("🖨️ Download Bill (HTML)", data=html_bill,
                                   file_name=f"{st.session_state.bill_number}.html",
                                   mime="text/html", use_container_width=True)
            with col_w:
                wa_url = whatsapp_share_url(phone_final, st.session_state.bill_number, net_total)
                if wa_url:
                    st.link_button("📲 Share on WhatsApp", wa_url, use_container_width=True)

            # Reset for next bill
            st.session_state.cart = []
            st.session_state.bill_number = generate_bill_number()
            st.session_state.pop("autofill_name", None)
            st.session_state.pop("autofill_phone", None)
            st.session_state.pop("discount_input", None)

    else:
        st.info("🛒 Cart empty — dishes add pannunga")

    # ── Bill Search ───────────────────────────────────────────────────────────
    st.divider()
    with st.expander("🔍 Search Old Bills"):
        search_term = st.text_input("Bill number or phone number enter pannunga")
        if search_term:
            orders = fetch_all("orders")
            results = [o for o in orders if
                       search_term in str(o.get("bill_number","")) or
                       search_term in str(o.get("phone_number",""))]
            if results:
                st.dataframe(pd.DataFrame(results), use_container_width=True)
            else:
                st.info("No orders found")
