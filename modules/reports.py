import calendar
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from utils.db import fetch_all
from utils.helpers import get_bom_cost, normalize_base_unit, convert_to_base_qty

# ── P&L Category Map ────────────────────────────────────────────────────────
# label -> (accounts.type, [accounts.category values], is_fixed_monthly_expense)
# Fixed = one-time lump entries (Rent/Salary/etc.) that need calendar-month
# proration to be fair across any custom date range. Everything else is
# already date-stamped per transaction and can be summed directly.
PNL_CATEGORIES = {
    "Sales":            ("Revenue", ["Sales"], False),
    "Purchases":        ("Expense", ["Purchase"], False),
    "Rent":             ("Expense", ["Rent"], True),
    "EB Bills":         ("Expense", ["EB Bill"], True),
    "Salaries":         ("Expense", ["Salary"], True),
    "Transports":       ("Expense", ["Transport"], True),
    "Gas Bills":        ("Expense", ["Gas Bill"], True),
    "Water Bills":      ("Expense", ["Water Bill"], True),
    "Wifi Bill":        ("Expense", ["Wifi Bill"], True),
    "Advertisements":   ("Expense", ["Advertisement"], True),
    "Maintenance":      ("Expense", ["Maintenance"], True),
    "Others":           ("Expense", ["Other"], True),
    "Food Wastes":      ("Expense", ["Raw Material Loss", "Cooked Item Waste", "Complimentary", "Wastage"], False),
    "Platform Charges": ("Expense", ["Platform Commission"], False),
    "Discounts":        ("Expense", ["Discount"], False),
}


def _days_in_month(d):
    return calendar.monthrange(d.year, d.month)[1]


def _month_bounds(d):
    start = d.replace(day=1)
    end = d.replace(day=_days_in_month(d))
    return str(start), str(end)


def reports_page():
    st.markdown("## 📊 Report Analytics")

    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("📅 From Date", value=date.today() - timedelta(days=30))
    with col2:
        to_date = st.date_input("📅 To Date", value=date.today())

    # Load data
    orders    = fetch_all("orders")
    acc_data  = fetch_all("accounts")   # unfiltered — needed for fixed-expense proration
    sku_data  = fetch_all("sku_master")
    menu_data = fetch_all("menu_master")

    # Filter by date range
    def in_range(d):
        try:
            return str(from_date) <= str(d) <= str(to_date)
        except:
            return False

    orders_f = [o for o in orders if in_range(o.get("date"))]
    acc_f    = [a for a in acc_data if in_range(a.get("date"))]

    if not orders_f and not acc_f:
        st.warning("⚠️ Selected date range la data illai")
        return

    orders_df = pd.DataFrame(orders_f) if orders_f else pd.DataFrame()
    acc_df    = pd.DataFrame(acc_f)    if acc_f    else pd.DataFrame()

    report = st.selectbox("Select Report", [
        "📊 P&L Summary",
        "📅 Working Days Summary",
        "🍲 Dish Performance",
        "👥 CRM Customer Retention",
        "📱 Platform Sales",
        "🗑️ Wastage Analysis",
        "💸 Expenses Breakdown",
        "🛑 Dead Stock Audit",
        "📦 Per Item Profit Calculator",
        "🧩 Sellable Units by Stock",
        "🏆 Best/Worst Dishes"
    ])

    st.divider()

    # ── P&L Summary ───────────────────────────────────────────────────────────
    if report == "📊 P&L Summary":
        st.markdown("### 📊 Profit & Loss Summary")
        st.caption("Fixed expenses (Rent/Salary/EB Bill/etc.) prorated using the calendar month of 'From Date'. "
                   "Everything else uses actual entries within the selected range.")

        selected = st.multiselect(
            "➕ Add Categories to Compare",
            options=list(PNL_CATEGORIES.keys()),
            default=list(PNL_CATEGORIES.keys()),
            key="pnl_cats"
        )

        if not selected:
            st.info("Konjam category select pannunga report paakka")
        else:
            range_days = max(1, (to_date - from_date).days + 1)
            m_start, m_end = _month_bounds(from_date)

            rows = []
            for label in selected:
                typ, cats, is_fixed = PNL_CATEGORIES[label]
                if is_fixed:
                    month_entries = [a for a in acc_data if a.get("category") in cats
                                      and m_start <= str(a.get("date", "")) <= m_end]
                    if not month_entries:
                        # fallback: most recent month that actually has entries for this category
                        all_cat_entries = sorted(
                            [a for a in acc_data if a.get("category") in cats],
                            key=lambda x: str(x.get("date", "")), reverse=True
                        )
                        if all_cat_entries:
                            fb_date = pd.to_datetime(all_cat_entries[0]["date"]).date()
                            fb_start, fb_end = _month_bounds(fb_date)
                            month_entries = [a for a in acc_data if a.get("category") in cats
                                              and fb_start <= str(a.get("date", "")) <= fb_end]
                            days_ref = _days_in_month(fb_date)
                        else:
                            days_ref = _days_in_month(from_date)
                    else:
                        days_ref = _days_in_month(from_date)
                    month_total = sum(float(a.get("amount", 0) or 0) for a in month_entries)
                    daily_rate = (month_total / days_ref) if days_ref else 0
                    amount = round(daily_rate * range_days, 2)
                else:
                    entries = [a for a in acc_f if a.get("category") in cats]
                    amount = round(sum(float(a.get("amount", 0) or 0) for a in entries), 2)

                rows.append({"Category": label, "Type": typ, "Fixed": is_fixed, "Amount": amount})

            pnl_df = pd.DataFrame(rows)
            total_sales    = pnl_df[pnl_df["Type"] == "Revenue"]["Amount"].sum()
            variable_costs = pnl_df[(pnl_df["Type"] == "Expense") & (~pnl_df["Fixed"])]["Amount"].sum()
            fixed_costs    = pnl_df[(pnl_df["Type"] == "Expense") & (pnl_df["Fixed"])]["Amount"].sum()

            gross_profit = total_sales - variable_costs
            gross_margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0
            net_profit   = total_sales - variable_costs - fixed_costs
            net_margin   = (net_profit / total_sales * 100) if total_sales > 0 else 0

            daily_fixed_cost = fixed_costs / range_days
            daily_breakeven  = (daily_fixed_cost / (gross_margin / 100)) if gross_margin > 0 else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Sales", f"₹{total_sales:,.2f}")
            c2.metric("💸 Variable Costs", f"₹{variable_costs:,.2f}")
            c3.metric("🏢 Fixed Costs (prorated)", f"₹{fixed_costs:,.2f}")

            c4, c5, c6 = st.columns(3)
            c4.metric("📈 Gross Margin", f"{gross_margin:.1f}%", help="(Sales − Variable Costs) / Sales")
            c5.metric("📊 Net Profit", f"₹{net_profit:,.2f}", delta=f"{net_margin:.1f}% net margin",
                      delta_color="normal" if net_profit >= 0 else "inverse")
            c6.metric("⚖️ Daily Breakeven Revenue", f"₹{daily_breakeven:,.2f}",
                      help="Revenue needed per day to cover that day's fixed cost share at current gross margin")

            st.dataframe(pnl_df[["Category", "Type", "Amount"]], use_container_width=True)

            # ── Trend chart: granularity auto-picked by range size, actual entries only ──
            range_days_span = (to_date - from_date).days + 1
            if range_days_span <= 31:
                granularity = "Daily"
            elif range_days_span <= 180:
                granularity = "Weekly"
            else:
                granularity = "Monthly"

            chart_parts = []
            if not acc_df.empty:
                acc_df_c = acc_df.copy()
                acc_df_c["amount"] = acc_df_c["amount"].astype(float)
                acc_df_c["dt"] = pd.to_datetime(acc_df_c["date"])
                for label in selected:
                    _, cats, _ = PNL_CATEGORIES[label]
                    sub = acc_df_c[acc_df_c["category"].isin(cats)]
                    if sub.empty:
                        continue
                    sub = sub.copy()
                    if granularity == "Daily":
                        sub["bucket"] = sub["dt"].dt.strftime("%Y-%m-%d")
                    elif granularity == "Weekly":
                        sub["bucket"] = sub["dt"].dt.to_period("W").apply(lambda p: p.start_time.strftime("%Y-%m-%d"))
                    else:
                        sub["bucket"] = sub["dt"].dt.to_period("M").astype(str)
                    grouped = sub.groupby("bucket")["amount"].sum().reset_index()
                    grouped["Category"] = label
                    chart_parts.append(grouped)

            if chart_parts:
                chart_df = pd.concat(chart_parts, ignore_index=True)
                fig = px.line(chart_df, x="bucket", y="amount", color="Category", markers=True,
                              title=f"P&L Trend ({granularity} — actual entries)")
                for trace in fig.data:
                    if trace.name == "Sales":
                        trace.update(line=dict(color="#2ecc71", width=4))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Chart-ku data illai selected categories la")

    # ── Working Days Summary ──────────────────────────────────────────────────
    elif report == "📅 Working Days Summary":
        st.markdown("### 📅 Working Days Summary")
        if not orders_df.empty:
            daily = orders_df.groupby("date").agg(
                Orders=("id", "count"),
                Revenue=("amount", lambda x: x.astype(float).sum())
            ).reset_index()
            working_days = len(daily)
            avg_revenue  = daily["Revenue"].mean()
            avg_orders   = daily["Orders"].mean()

            c1, c2, c3 = st.columns(3)
            c1.metric("📅 Working Days", working_days)
            c2.metric("📦 Avg Orders/Day", f"{avg_orders:.1f}")
            c3.metric("💰 Avg Revenue/Day", f"₹{avg_revenue:,.2f}")

            fig = px.line(daily, x="date", y="Revenue", markers=True,
                          title="Daily Revenue Trend")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(daily, use_container_width=True)
        else:
            st.info("No orders in this range")

    # ── Dish Performance ──────────────────────────────────────────────────────
    elif report == "🍲 Dish Performance":
        st.markdown("### 🍲 Dish Performance")
        if not orders_df.empty:
            menu_price_map = {m["Dish Name"]: float(m.get("Price", 0) or 0) for m in menu_data if m.get("Dish Name")}
            dish_counts  = {}
            dish_revenue = {}
            for _, row in orders_df.iterrows():
                summary = str(row.get("items_summary", ""))
                items = summary.split(",")
                for item in items:
                    item = item.strip()
                    if "×" in item:
                        parts = item.split("×")
                        dish = parts[0].strip()
                        try:
                            qty = int(parts[1].strip())
                        except:
                            qty = 1
                        price = menu_price_map.get(dish, 0)
                        dish_counts[dish]  = dish_counts.get(dish, 0) + qty
                        dish_revenue[dish] = dish_revenue.get(dish, 0) + (qty * price)

            perf_df = pd.DataFrame({
                "Dish": list(dish_counts.keys()),
                "Qty Sold": list(dish_counts.values()),
                "Revenue": [round(dish_revenue.get(d, 0), 2) for d in dish_counts.keys()]
            }).sort_values("Qty Sold", ascending=False)

            calc_total   = perf_df["Revenue"].sum()
            actual_total = orders_df["amount"].astype(float).sum()
            diff = actual_total - calc_total
            if abs(diff) > 1:
                st.caption(f"ℹ️ Menu-price revenue ₹{calc_total:,.2f} vs actual billed ₹{actual_total:,.2f} "
                          f"(diff ₹{diff:,.2f} — discounts / menu price changes)")

            fig = px.bar(perf_df.head(15), x="Dish", y="Qty Sold",
                         title="Top 15 Dishes by Quantity", color="Qty Sold",
                         color_continuous_scale="Oranges")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(perf_df, use_container_width=True)
        else:
            st.info("No orders in this range")

    # ── CRM Customer Retention (RFM) ──────────────────────────────────────────
    elif report == "👥 CRM Customer Retention":
        st.markdown("### 👥 CRM — Customer Retention (RFM)")
        all_orders = pd.DataFrame(orders) if orders else pd.DataFrame()
        if not all_orders.empty:
            all_orders = all_orders.copy()
            all_orders["amount"] = all_orders["amount"].astype(float)
            all_orders["cust_key"] = all_orders.apply(
                lambda r: str(r.get("phone_number")) if r.get("phone_number") and str(r.get("phone_number")) != "N/A"
                          else f"NAME:{r.get('customer_name', 'Unknown')}",
                axis=1
            )

            cust = all_orders.groupby("cust_key").agg(
                Visits=("id", "count"),
                TotalSpend=("amount", "sum"),
                LastVisit=("date", "max"),
                Name=("customer_name", "first"),
                Phone=("phone_number", "first")
            ).reset_index()
            cust["Avg Order Value"] = (cust["TotalSpend"] / cust["Visits"]).round(2)
            cust["Recency (days)"] = cust["LastVisit"].apply(
                lambda d: (date.today() - pd.to_datetime(d).date()).days
            )

            def _quintile(series, ascending):
                ranks = series.rank(method="first", ascending=ascending)
                return pd.cut(ranks, bins=5, labels=[1, 2, 3, 4, 5]).astype(int)

            def _simple(series, ascending):
                med = series.median()
                return series.apply(lambda x: 3 if ((x >= med) if ascending else (x <= med)) else 1)

            if len(cust) >= 5:
                cust["R_Score"] = _quintile(cust["Recency (days)"], ascending=False)
                cust["F_Score"] = _quintile(cust["Visits"], ascending=True)
                cust["M_Score"] = _quintile(cust["TotalSpend"], ascending=True)
            else:
                cust["R_Score"] = _simple(cust["Recency (days)"], ascending=False)
                cust["F_Score"] = _simple(cust["Visits"], ascending=True)
                cust["M_Score"] = _simple(cust["TotalSpend"], ascending=True)

            cust["RFM_Total"] = cust["R_Score"] + cust["F_Score"] + cust["M_Score"]

            def _segment(row):
                if row["RFM_Total"] >= 12:
                    return "🏆 Champion"
                elif row["RFM_Total"] >= 9:
                    return "⭐ Loyal"
                elif row["Recency (days)"] > 60:
                    return "⚠️ At Risk"
                elif row["Visits"] == 1:
                    return "🆕 New"
                else:
                    return "🔻 Needs Attention"

            cust["Segment"] = cust.apply(_segment, axis=1)

            loyal    = cust[cust["Visits"] >= 3]
            one_time = cust[cust["Visits"] == 1]

            c1, c2, c3 = st.columns(3)
            c1.metric("👥 Total Customers", len(cust))
            c2.metric("⭐ Loyal (3+ visits)", len(loyal))
            c3.metric("1️⃣ One-time Customers", len(one_time))

            fig = px.histogram(cust, x="Visits", title="Customer Visit Frequency Distribution")
            st.plotly_chart(fig, use_container_width=True)

            seg_counts = cust["Segment"].value_counts().reset_index()
            seg_counts.columns = ["Segment", "Count"]
            fig2 = px.bar(seg_counts, x="Segment", y="Count", title="RFM Segments", color="Segment")
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("#### Top 20 Customers (by RFM)")
            cols = ["Name", "Phone", "Visits", "TotalSpend", "Avg Order Value",
                    "LastVisit", "Recency (days)", "R_Score", "F_Score", "M_Score", "Segment"]
            st.dataframe(cust.sort_values("RFM_Total", ascending=False).head(20)[cols],
                         use_container_width=True)
        else:
            st.info("No customer data")

    # ── Platform Sales ────────────────────────────────────────────────────────
    elif report == "📱 Platform Sales":
        st.markdown("### 📱 Platform Sales Breakdown")
        if not orders_df.empty:
            plat = orders_df.groupby("platform").agg(
                Orders=("id", "count"),
                Revenue=("amount", lambda x: x.astype(float).sum())
            ).reset_index()

            c1, c2 = st.columns(2)
            with c1:
                fig1 = px.pie(plat, values="Orders", names="platform",
                              title="Orders by Platform", hole=0.4,
                              color_discrete_sequence=px.colors.qualitative.Set2)
                st.plotly_chart(fig1, use_container_width=True)
            with c2:
                fig2 = px.bar(plat, x="platform", y="Revenue",
                              title="Revenue by Platform",
                              color_discrete_sequence=["#e65c00"])
                st.plotly_chart(fig2, use_container_width=True)

            st.dataframe(plat, use_container_width=True)
        else:
            st.info("No orders in this range")

    # ── Wastage Analysis ──────────────────────────────────────────────────────
    elif report == "🗑️ Wastage Analysis":
        st.markdown("### 🗑️ Wastage Analysis")
        if not acc_df.empty:
            waste_df = acc_df[acc_df["category"].isin(
                ["Raw Material Loss", "Cooked Item Waste", "Complimentary", "Wastage"]
            )]
            if not waste_df.empty:
                waste_df = waste_df.copy()
                waste_df["amount"] = waste_df["amount"].astype(float)
                total_waste = waste_df["amount"].sum()
                st.metric("💸 Total Wastage Cost", f"₹{total_waste:,.2f}")

                by_cat = waste_df.groupby("category")["amount"].sum().reset_index()
                by_cat["category"] = by_cat["category"].replace({"Wastage": "Wastage (Legacy — pre-split entries)"})
                fig = px.pie(by_cat, values="amount", names="category",
                             title="Wastage by Type")
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(waste_df[["date", "category", "item_name", "amount", "qty", "unit", "notes"]]
                             .sort_values("date", ascending=False), use_container_width=True)
            else:
                st.success("✅ No wastage in this period")
        else:
            st.info("No data in this range")

    # ── Expenses Breakdown ────────────────────────────────────────────────────
    elif report == "💸 Expenses Breakdown":
        st.markdown("### 💸 Expenses Breakdown")
        if not acc_df.empty:
            exp_df = acc_df[acc_df["type"] == "Expense"].copy()
            if not exp_df.empty:
                exp_df["amount"] = exp_df["amount"].astype(float)
                total_exp = exp_df["amount"].sum()
                st.metric("💸 Total Expenses", f"₹{total_exp:,.2f}")

                by_cat = exp_df.groupby("category")["amount"].sum().reset_index()
                fig = px.bar(by_cat.sort_values("amount", ascending=False),
                             x="category", y="amount",
                             title="Expenses by Category",
                             color_discrete_sequence=["#e74c3c"])
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(exp_df[["date", "category", "item_name", "amount", "notes"]]
                             .sort_values("date", ascending=False), use_container_width=True)
            else:
                st.info("No expense entries")
        else:
            st.info("No data in this range")

    # ── Dead Stock Audit ───────────────────────────────────────────────────────
    elif report == "🛑 Dead Stock Audit":
        st.markdown("### 🛑 Dead Stock Audit")
        st.caption("🟡 60-89 days unused · 🔴 90+ days unused")

        all_orders = pd.DataFrame(orders) if orders else pd.DataFrame()
        bom_data = fetch_all("bom_master")

        dish_last_sold = {}
        if not all_orders.empty:
            for _, row in all_orders.iterrows():
                summary = str(row.get("items_summary", ""))
                d = str(row.get("date", ""))
                for item in summary.split(","):
                    if "×" in item:
                        dish = item.split("×")[0].strip()
                        if dish not in dish_last_sold or d > dish_last_sold[dish]:
                            dish_last_sold[dish] = d

        def _days_since(d_str):
            if not d_str:
                return 99999
            return (date.today() - pd.to_datetime(d_str).date()).days

        def _bucket(days):
            if days >= 90:
                return "🔴 90+ days"
            elif days >= 60:
                return "🟡 60-89 days"
            return None

        def _highlight(val):
            if isinstance(val, str) and "🔴" in val:
                return "background-color:#f8d7da"
            elif isinstance(val, str) and "🟡" in val:
                return "background-color:#fff3cd"
            return ""

        # Menu Item Dead Stock
        menu_dead = []
        for m in menu_data:
            dish = m.get("Dish Name", "")
            last_sold = dish_last_sold.get(dish)
            d = _days_since(last_sold)
            b = _bucket(d)
            if b:
                menu_dead.append({
                    "Dish": dish, "Category": m.get("Category", ""),
                    "Last Sold": last_sold or "Never", "Days Inactive": d, "Status": b
                })

        # Ingredient last-used = latest sale date among dishes that use it
        ingredient_last_used = {}
        for b in bom_data:
            ing  = b.get("Ingerdient Name", "")
            dish = b.get("Dish Name", "")
            last_sold = dish_last_sold.get(dish)
            if last_sold and (ing not in ingredient_last_used or last_sold > ingredient_last_used[ing]):
                ingredient_last_used[ing] = last_sold

        # SKU Dead Stock
        sku_dead = []
        for s in sku_data:
            ing = s.get("Ingerdient Name", "")
            if float(s.get("current_stock", 0) or 0) <= 0:
                continue
            last_used = ingredient_last_used.get(ing)
            d = _days_since(last_used)
            b = _bucket(d)
            if b:
                sku_dead.append({
                    "Ingredient": ing, "Stock": s.get("current_stock"), "Unit": s.get("Purchase unit"),
                    "Market Price": s.get("Market Price"), "Last Used": last_used or "Never",
                    "Days Inactive": d, "Status": b
                })

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"#### 🧂 SKU Dead Stock ({len(sku_dead)})")
            if sku_dead:
                sku_dead_df = pd.DataFrame(sku_dead).sort_values("Days Inactive", ascending=False)
                st.dataframe(sku_dead_df.style.map(_highlight, subset=["Status"]), use_container_width=True)
            else:
                st.success("✅ No dead SKU stock")
        with col2:
            st.markdown(f"#### 🍲 Menu Item Dead Stock ({len(menu_dead)})")
            if menu_dead:
                menu_dead_df = pd.DataFrame(menu_dead).sort_values("Days Inactive", ascending=False)
                st.dataframe(menu_dead_df.style.map(_highlight, subset=["Status"]), use_container_width=True)
            else:
                st.success("✅ No dead menu items")

    # ── Per Item Profit Calculator ────────────────────────────────────────────
    elif report == "📦 Per Item Profit Calculator":
        st.markdown("### 📦 Per Item Profit Calculator")
        dish_names = [m["Dish Name"] for m in menu_data if m.get("Dish Name")]
        price_map  = {m["Dish Name"]: float(m.get("Price", 0) or 0) for m in menu_data if m.get("Dish Name")}

        sel_dish = st.selectbox("🍲 Select Dish", dish_names, key="profit_calc_dish")
        if sel_dish:
            selling_price = price_map.get(sel_dish, 0)
            making_cost   = get_bom_cost(sel_dish)
            profit        = selling_price - making_cost
            margin_pct    = (profit / selling_price * 100) if selling_price > 0 else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Selling Price", f"₹{selling_price:.2f}")
            c2.metric("🧂 Making Cost (live market price)", f"₹{making_cost:.2f}")
            c3.metric("📈 Profit", f"₹{profit:.2f}", delta=f"{margin_pct:.1f}% margin",
                      delta_color="normal" if profit >= 0 else "inverse")

    # ── Sellable Units by Stock ───────────────────────────────────────────────
    elif report == "🧩 Sellable Units by Stock":
        st.markdown("### 🧩 Sellable Units by Stock")
        st.caption("Ipo kaila irukura SKU vachi, dish/category wise evlo units sell panna mudiyum")

        bom_data = fetch_all("bom_master")
        sku_map  = {s["Ingerdient Name"]: s for s in sku_data}

        dish_bom = {}
        for b in bom_data:
            dish_bom.setdefault(b.get("Dish Name", ""), []).append(b)

        categories = sorted(set(m.get("Category", "") for m in menu_data if m.get("Category")))
        cat_filter = st.multiselect("📂 Category Filter (empty = all)", categories, key="sellable_cat_filter")

        sellable = []
        for m in menu_data:
            dish = m.get("Dish Name", "")
            category = m.get("Category", "")
            if cat_filter and category not in cat_filter:
                continue
            boms = dish_bom.get(dish, [])
            if not boms:
                continue
            max_units = []
            for b in boms:
                ing = b.get("Ingerdient Name", "")
                req_qty = float(b.get("Required quantity", 0) or 0)
                unit = b.get("Unit", "gm")
                sku = sku_map.get(ing, {})
                base_unit = normalize_base_unit(sku.get("Purchase unit", "gm"))
                req_qty_base = convert_to_base_qty(req_qty, unit, base_unit)
                stock = float(sku.get("current_stock", 0) or 0)
                max_units.append(int(stock // req_qty_base) if req_qty_base > 0 else 0)
            sellable.append({
                "Dish": dish, "Category": category,
                "Max Sellable Units": min(max_units) if max_units else 0
            })

        if sellable:
            sell_df = pd.DataFrame(sellable).sort_values("Max Sellable Units")
            fig = px.bar(sell_df.sort_values("Max Sellable Units", ascending=False).head(20),
                         x="Dish", y="Max Sellable Units", title="Max Sellable Units (Current Stock)",
                         color="Max Sellable Units", color_continuous_scale="Greens")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(sell_df, use_container_width=True)
        else:
            st.info("No BOM/menu data available for selected filter")

    # ── Best/Worst Dishes ─────────────────────────────────────────────────────
    elif report == "🏆 Best/Worst Dishes":
        st.markdown("### 🏆 Best / Worst Performing Dishes")
        if not orders_df.empty:
            dish_counts = {}
            for _, row in orders_df.iterrows():
                summary = str(row.get("items_summary", ""))
                for item in summary.split(","):
                    item = item.strip()
                    if "×" in item:
                        parts = item.split("×")
                        dish = parts[0].strip()
                        try:
                            qty = int(parts[1].strip())
                        except:
                            qty = 1
                        dish_counts[dish] = dish_counts.get(dish, 0) + qty

            counts_df = pd.DataFrame({"Dish": list(dish_counts.keys()), "Qty Sold": list(dish_counts.values())})
            best_df  = counts_df.sort_values("Qty Sold", ascending=False).head(20)
            worst_df = counts_df[counts_df["Qty Sold"] <= 2].sort_values("Qty Sold")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🏆 Best (Top 20)")
                st.dataframe(best_df, use_container_width=True)
            with col2:
                st.markdown(f"#### 📉 Worst (Qty ≤ 2) — {len(worst_df)} dishes")
                st.dataframe(worst_df, use_container_width=True)
        else:
            st.info("No orders in this range")
