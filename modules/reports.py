import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from utils.db import fetch_all
from utils.helpers import get_bom_cost

def reports_page():
    st.markdown("## 📊 Report Analytics")

    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("📅 From Date", value=date.today() - timedelta(days=30))
    with col2:
        to_date = st.date_input("📅 To Date", value=date.today())

    # Load data
    orders   = fetch_all("orders")
    acc_data = fetch_all("accounts")
    sku_data = fetch_all("sku_master")
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
        "🛑 Dead Stock (60-Day Audit)"
    ])

    st.divider()

    # ── P&L Summary ───────────────────────────────────────────────────────────
    if report == "📊 P&L Summary":
        st.markdown("### 📊 Profit & Loss Summary")
        if not acc_df.empty:
            revenue = acc_df[acc_df["type"] == "Revenue"]["amount"].astype(float).sum()
            expense = acc_df[acc_df["type"] == "Expense"]["amount"].astype(float).sum()
            profit  = revenue - expense
            margin  = (profit / revenue * 100) if revenue > 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 Revenue",  f"₹{revenue:,.2f}")
            c2.metric("💸 Expenses", f"₹{expense:,.2f}")
            c3.metric("📈 Net Profit", f"₹{profit:,.2f}",
                      delta=f"{margin:.1f}% margin",
                      delta_color="normal" if profit >= 0 else "inverse")
            c4.metric("📦 Orders", len(orders_f))

            st.divider()
            # Daily revenue vs expense chart
            if not acc_df.empty:
                daily = acc_df.groupby(["date","type"])["amount"].sum().reset_index()
                fig = px.bar(daily, x="date", y="amount", color="type",
                             barmode="group", title="Daily Revenue vs Expenses",
                             color_discrete_map={"Revenue":"#2ecc71","Expense":"#e74c3c"})
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No accounts data for this range")

    # ── Working Days Summary ──────────────────────────────────────────────────
    elif report == "📅 Working Days Summary":
        st.markdown("### 📅 Working Days Summary")
        if not orders_df.empty:
            daily = orders_df.groupby("date").agg(
                Orders=("id","count"),
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
            dish_counts = {}
            dish_revenue = {}
            for _, row in orders_df.iterrows():
                summary = str(row.get("items_summary",""))
                amount  = float(row.get("amount", 0))
                items   = summary.split(",")
                for item in items:
                    item = item.strip()
                    if "×" in item:
                        parts = item.split("×")
                        dish  = parts[0].strip()
                        try:
                            qty = int(parts[1].strip())
                        except:
                            qty = 1
                        dish_counts[dish]   = dish_counts.get(dish, 0) + qty
                        dish_revenue[dish]  = dish_revenue.get(dish, 0) + (amount / len(items))

            perf_df = pd.DataFrame({
                "Dish": list(dish_counts.keys()),
                "Qty Sold": list(dish_counts.values()),
                "Est Revenue": [dish_revenue.get(d, 0) for d in dish_counts.keys()]
            }).sort_values("Qty Sold", ascending=False)

            fig = px.bar(perf_df.head(15), x="Dish", y="Qty Sold",
                         title="Top 15 Dishes by Quantity", color="Qty Sold",
                         color_continuous_scale="Oranges")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(perf_df, use_container_width=True)
        else:
            st.info("No orders in this range")

    # ── CRM Customer Retention ────────────────────────────────────────────────
    elif report == "👥 CRM Customer Retention":
        st.markdown("### 👥 CRM — Customer Retention")
        all_orders = pd.DataFrame(orders) if orders else pd.DataFrame()
        if not all_orders.empty:
            cust = all_orders.groupby("customer_name").agg(
                Visits=("id","count"),
                TotalSpend=("amount", lambda x: x.astype(float).sum()),
                LastVisit=("date","max"),
                Phone=("phone_number","first")
            ).reset_index().sort_values("Visits", ascending=False)
            cust["Avg Order Value"] = (cust["TotalSpend"] / cust["Visits"]).round(2)

            loyal    = cust[cust["Visits"] >= 3]
            one_time = cust[cust["Visits"] == 1]

            c1, c2, c3 = st.columns(3)
            c1.metric("👥 Total Customers", len(cust))
            c2.metric("⭐ Loyal (3+ visits)", len(loyal))
            c3.metric("1️⃣ One-time Customers", len(one_time))

            fig = px.histogram(cust, x="Visits", title="Customer Visit Frequency Distribution")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Top 20 Customers")
            st.dataframe(cust.head(20)[["customer_name","Phone","Visits","TotalSpend","Avg Order Value","LastVisit"]],
                         use_container_width=True)
        else:
            st.info("No customer data")

    # ── Platform Sales ────────────────────────────────────────────────────────
    elif report == "📱 Platform Sales":
        st.markdown("### 📱 Platform Sales Breakdown")
        if not orders_df.empty:
            plat = orders_df.groupby("platform").agg(
                Orders=("id","count"),
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
            waste_df = acc_df[acc_df["category"].isin(["Wastage","Complimentary"])]
            if not waste_df.empty:
                total_waste = waste_df["amount"].astype(float).sum()
                st.metric("💸 Total Wastage Cost", f"₹{total_waste:,.2f}")

                by_cat = waste_df.groupby("category")["amount"].sum().reset_index()
                fig = px.pie(by_cat, values="amount", names="category",
                             title="Wastage by Type")
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(waste_df[["date","category","item_name","amount","qty","unit","notes"]]
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

                st.dataframe(exp_df[["date","category","item_name","amount","notes"]]
                             .sort_values("date", ascending=False), use_container_width=True)
            else:
                st.info("No expense entries")
        else:
            st.info("No data in this range")

    # ── Dead Stock Audit ──────────────────────────────────────────────────────
    elif report == "🛑 Dead Stock (60-Day Audit)":
        st.markdown("### 🛑 Dead Stock — 60-Day Inactivity Audit")
        st.caption("Last 60 days la use aagatha SKU items — these are dead stock")

        cutoff = str(date.today() - timedelta(days=60))
        all_orders = pd.DataFrame(orders) if orders else pd.DataFrame()
        used_ingredients = set()

        if not all_orders.empty:
            recent_orders = all_orders[all_orders["date"] >= cutoff]
            bom_data = fetch_all("bom_master")
            recent_dishes = set()
            for _, row in recent_orders.iterrows():
                summary = str(row.get("items_summary",""))
                for item in summary.split(","):
                    if "×" in item:
                        recent_dishes.add(item.split("×")[0].strip())

            for b in bom_data:
                if b.get("Dish Name") in recent_dishes:
                    used_ingredients.add(b.get("Ingerdient Name",""))

        dead_stock = [s for s in sku_data
                      if s.get("Ingerdient Name") not in used_ingredients
                      and float(s.get("current_stock", 0)) > 0]

        if dead_stock:
            dead_df = pd.DataFrame(dead_stock)[["Ingerdient Name","current_stock","Purchase unit","Market Price","Category"]]
            dead_df.columns = ["Ingredient","Stock","Unit","Market Price (₹)","Category"]
            st.warning(f"⚠️ {len(dead_stock)} dead stock items found (60-day inactivity)")
            st.dataframe(dead_df, use_container_width=True)
        else:
            st.success("✅ No dead stock found — all items used within 60 days!")
