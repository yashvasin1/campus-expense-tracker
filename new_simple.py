import streamlit as st
import pandas as pd
import plotly.express as px
import re
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. VIP GUEST LIST ---
VIP_USERS = {
    "tester-1": "1234",
    "tester-2": "1234",
    "tester-3": "1234",
    "tester-4": "1234",
    "professor":"1234"
}

# --- 2. GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("Campus_Expenses_DB")

# --- 3. CLOUD DATABASE FUNCTIONS ---
def fetch_records(username, sheet_client):
    try:
        user_tab = sheet_client.worksheet(username)
        data = user_tab.get_all_records()
        if not data:
            return pd.DataFrame(columns=["Date", "Category", "Cost", "Details"])
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Error: Could not find a tab named '{username}' in the Google Sheet.")
        return pd.DataFrame(columns=["Date", "Category", "Cost", "Details"])

def insert_record(username, sheet_client, d, cat, amt, desc):
    user_tab = sheet_client.worksheet(username)
    new_row = [str(d), cat, float(amt), desc]
    user_tab.append_row(new_row)

def update_entire_sheet(username, sheet_client, df):
    user_tab = sheet_client.worksheet(username)
    user_tab.clear()
    
    # Clean dataframe to prevent Google Sheets upload errors
    df = df.fillna("")
    df["Date"] = df["Date"].astype(str)
    
    # Write the headers and the new data back to the sheet
    user_tab.update([df.columns.values.tolist()] + df.values.tolist())

def main():
    st.set_page_config(page_title="Campus Finance", layout="wide")
    
    # --- 100% SAFE CSS ---
    hide_st_style = """
                <style>
                /* Hide the bottom footer */
                [data-testid="stFooter"] {visibility: hidden !important;}
                
                /* Hide the colored decoration line at the top */
                [data-testid="stDecoration"] {visibility: hidden !important;}
                
                /* Hide the floating Streamlit Cloud badge at the bottom right */
                .viewerBadge_container__1QSob,
                .styles_viewerBadge__1yB5_,
                .viewerBadge_link__1S137,
                .viewerBadge_text__1JaDK {
                    display: none !important;
                }
                </style>
                """
    st.markdown(hide_st_style, unsafe_allow_html=True)
    # Connect to Google Sheets
    try:
        sheet_client = init_connection()
    except Exception as e:
        st.error("Google Sheets connection failed. Please check your Streamlit Secrets.")
        st.stop()
    
    # --- LOGIN SYSTEM ---
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.title("🔒 Campus Expense Tracker (Private)")
        st.write("Please log in to access your personal dashboard.")
        
        username_input = st.text_input("Username").lower()
        password_input = st.text_input("Password", type="password")
        
        if st.button("Login"):
            if username_input in VIP_USERS and VIP_USERS[username_input] == password_input:
                st.session_state["logged_in"] = True
                st.session_state["username"] = username_input
                st.rerun()
            else:
                st.error("Incorrect username or password. Access Denied.")
                
    # --- THE MAIN APP ---
    else:
        current_user = st.session_state["username"]
        
        st.sidebar.write(f"### 👋 Welcome, {current_user.title()}!")
        st.sidebar.write("---")
            
        records = fetch_records(current_user, sheet_client)
        
        if len(records) > 0:
            # --- ADD THIS LINE TO FORCE 'COST' TO BE A REAL NUMBER ---
            records["Cost"] = pd.to_numeric(records["Cost"].astype(str).str.replace('₹', '', regex=False).str.replace(',', '', regex=False).str.strip(), errors='coerce').fillna(0.0)
            
            records["Date"] = pd.to_datetime(records["Date"], errors='coerce')
            records = records.dropna(subset=["Date"])
            records["Month_Year"] = records["Date"].dt.to_period("M").astype(str)
            records["Year"] = records["Date"].dt.year

        st.sidebar.header("1. Goals & Limits")
        monthly_limit = st.sidebar.number_input("Monthly Budget (₹)", min_value=0.0, value=5000.0)
        yearly_goal = st.sidebar.number_input("Yearly Savings Goal (₹)", min_value=0.0, value=20000.0)

        # 1. Added gap="large" to create wide horizontal space between columns
        col_title, col_goal = st.columns([2.2, 1.8], gap="large")

        with col_title:
            st.title(f"📊 {current_user.title()}'s Expense Tracker")
            st.write("Keep track of your monthly allowance and spending")

        with col_goal:
            # 2. Added empty write() to push the Savings card down for perfect vertical alignment
            st.write("") 
            
            current_year = datetime.today().year
            total_saved = 0
            
            if len(records) > 0 and "Year" in records.columns:
                year_records = records[records["Year"] == current_year]
                
                if len(year_records) > 0:
                    total_deficits = 0
                    
                    for month in year_records["Month_Year"].unique():
                        month_spent = year_records[year_records["Month_Year"] == month]["Cost"].sum()
                        if month_spent > monthly_limit:
                            total_deficits += (month_spent - monthly_limit)
                        else:
                            total_saved += (monthly_limit - month_spent)
                    
                    st.metric(
                        label=f"🎯 {current_year} Savings Progress", 
                        value=f"₹{total_saved:,.2f} Saved", 
                        delta=f"Goal: ₹{yearly_goal:,.2f}",
                        delta_color="off"
                    )
                else:
                    st.metric(f"🎯 {current_year} Savings Progress", f"₹0 Saved", f"Goal: ₹{yearly_goal:,.2f}", delta_color="off")
            else:
                st.metric(f"🎯 {current_year} Savings Progress", f"₹0 Saved", f"Goal: ₹{yearly_goal:,.2f}", delta_color="off")

            if yearly_goal > 0:
                progress_fraction = max(0.0, min(total_saved / yearly_goal, 1.0))
                progress_percent = int(progress_fraction * 100)
                st.progress(progress_fraction, text=f"Goal Completion: {progress_percent}%")

        # --- SIDEBAR: DYNAMIC FORM ---
        st.sidebar.write("---")
        st.sidebar.header("2. Log a Purchase")

        default_categories = ["Snacks/Food", "Transport", "Shopping", "Fun/Movies", "College/Edu", "Misc"]
        
        if len(records) > 0:
            existing_categories = records["Category"].dropna().unique().tolist()
        else:
            existing_categories = []
            
        all_categories = default_categories.copy()
        for cat in existing_categories:
            if cat not in all_categories:
                all_categories.append(cat)
                
        all_categories.append("➕ Custom...")

        with st.sidebar.form("entry_form", clear_on_submit=True):
            input_date = st.date_input("Date of Purchase", datetime.today().date())
            input_cat = st.selectbox("Category", all_categories)
            custom_cat = st.text_input("Custom Category (if selected above)")
            input_cost = st.text_input("Cost (₹)", placeholder="e.g. 150")
            input_details = st.text_input("Details")
            
            save_btn = st.form_submit_button("Log It")
            
            if save_btn:
                try:
                    # Convert the text they typed into a valid number
                    final_cost = float(input_cost)
                    
                    if final_cost <= 0:
                        st.sidebar.error("Cost must be greater than 0.")
                    else:
                        final_category = input_cat
                        if input_cat == "➕ Custom...":
                            if custom_cat.strip() != "":
                                final_category = custom_cat.strip().title()
                            else:
                                final_category = "Misc" 
                                
                        insert_record(current_user, sheet_client, input_date, final_category, final_cost, input_details)
                        st.toast("Purchase logged successfully!", icon="✅")
                        st.rerun()
                        
                except ValueError:
                    # If they accidentally typed letters or left it blank
                    st.sidebar.error("Please enter a valid number for the cost.")
                        
                insert_record(current_user, sheet_client, input_date, final_category, input_cost, input_details)
                st.toast("Purchase logged successfully!", icon="✅")
                st.rerun()

        # --- SIDEBAR: SMS SCANNER ---
        st.sidebar.write("---")
        st.sidebar.header("📱 3. Smart SMS Reader")
        st.sidebar.caption("Paste one or multiple bank alerts below to test the automation.")

        default_text = "Account debited by Rs. 350.00 on 11-Jul for Zomato.\nAccount debited by ₹120.00 on 12-Jul for Uber."
        test_sms = st.sidebar.text_area("SMS Text:", default_text, height=150)

        if st.sidebar.button("Run Text Scanner"):
            expense_matches = list(re.finditer(r'(?:Rs\.?|INR|₹)\s*(\d+(?:\.\d+)?)', test_sms, re.IGNORECASE))
            
            if expense_matches:
                text_lower_full = test_sms.lower()
                success_count = 0
                
                food_kw = ["zomato", "swiggy", "blinkit", "zepto", "instamart", "kfc", "mcdonalds", "dominos", "cafe"]
                shop_kw = ["amazon", "flipkart", "myntra", "ajio", "zudio", "reliance", "croma", "mall"]
                trans_kw = ["uber", "ola", "rapido", "metro", "irctc", "bus", "train", "flight"]
                movie_kw = ["netflix", "pvr", "movie", "spotify", "bookmyshow", "prime"]
                
                for i, match in enumerate(expense_matches):
                    found_cash = float(match.group(1))
                    start_idx = max(0, match.start() - 50)
                    end_idx = min(len(test_sms), match.end() + 50)
                    context_text = text_lower_full[start_idx:end_idx]
                    
                    detected_category = "Misc"
                    if any(word in context_text for word in food_kw): detected_category = "Snacks/Food"
                    elif any(word in context_text for word in shop_kw): detected_category = "Shopping"
                    elif any(word in context_text for word in trans_kw): detected_category = "Transport"
                    elif any(word in context_text for word in movie_kw): detected_category = "Fun/Movies"
                    
                    insert_record(current_user, sheet_client, datetime.today().date(), detected_category, found_cash, "Auto-scanned")
                    st.toast(f"Match {i+1}: Detected ₹{found_cash} for {detected_category}.", icon="🤖")
                    success_count += 1
                
                if success_count > 0:
                    st.rerun()
            else:
                st.sidebar.error("Couldn't extract any valid numbers from that message.")

        # --- SIDEBAR: LOGOUT ---
        st.sidebar.write("---")
        if st.sidebar.button("🚪🚶 Logout"):
            st.session_state["logged_in"] = False
            st.rerun()

        # --- MAIN DASHBOARD AREA ---
        if len(records) == 0:
            st.info("Your tracker is empty. Add a purchase on the left to begin.")
        else:
            unique_months = sorted(records["Month_Year"].dropna().astype(str).unique(), reverse=True)
            
            col_m1, col_m2 = st.columns(2)
                       
            with col_m1:
                # --- SMART INDEX: AUTO-SELECT CURRENT MONTH BY DEFAULT ---
                current_m_str = datetime.today().strftime("%Y-%m")
                default_idx = unique_months.index(current_m_str) if current_m_str in unique_months else 0
                view_month = st.selectbox("View spending for:", unique_months, index=default_idx)
            with col_m2:
                compare_toggle = st.checkbox("Compare with another month")
                if compare_toggle:
                    default_compare = 1 if len(unique_months) > 1 else 0
                    compare_month = st.selectbox("Compare against:", unique_months, index=default_compare)

            monthly_records = records[records["Month_Year"] == view_month]
            total_out = monthly_records["Cost"].sum()
            balance = monthly_limit - total_out
            
            st.write("### Quick Stats")
            stat1, stat2 = st.columns(2)
            
            with stat1:
                if compare_toggle:
                    compare_records = records[records["Month_Year"] == compare_month]
                    compare_total = compare_records["Cost"].sum()
                    variance = total_out - compare_total
                    st.metric("Money Spent", f"₹{total_out:,.2f}", f"₹{variance:,.2f} vs {compare_month}", delta_color="inverse")
                else:
                    st.metric("Money Spent", f"₹{total_out:,.2f}")

            with stat2:
                if balance < 0:
                    st.metric("Remaining Balance", f"₹{balance:,.2f}", "Deficit!", delta_color="inverse")
                else:
                    st.metric("Remaining Balance", f"₹{balance:,.2f}", "Looking Good", delta_color="normal")
                    
            st.write("---")
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.write("#### Recent Activity")
                if len(monthly_records) > 0:
                    # Flip table upside-down first (newest entries on top), then sort by date
                    display_data = monthly_records[["Date", "Category", "Cost", "Details"]].iloc[::-1].sort_values(by="Date", ascending=False, kind="mergesort")
                    st.dataframe(display_data.head(10), hide_index=True)
                    
            with col_right:
                st.write("#### Spending by Category")
                if len(monthly_records) > 0:
                    grouped = monthly_records.groupby("Category")["Cost"].sum().reset_index()
                    donut = px.pie(grouped, values='Cost', names='Category', hole=0.4)
                    st.plotly_chart(donut, use_container_width=True)
                else:
                    st.write("No purchases logged this month.")
                    
            st.write("---")
            st.write("### 💡 Smart Insights")
            
            if balance < 0:
                st.error("🚨 You've exceeded your monthly budget! Put a pause on non-essential purchases.")
            elif total_out >= (0.8 * monthly_limit):
                st.warning("⚠️ You've spent over 80% of your budget. Time to pace yourself.")
            elif total_out > 0:
                st.success("✅ You're comfortably within your budget. Great job managing your money!")
            # --- MISSING BAR GRAPH SECTION ---
            st.write("---")
            with st.expander("📈 Monthly Spending Trends"):
                if len(records) > 0:
                    trend_data = records.groupby("Month_Year")["Cost"].sum().reset_index()
                    trend_data = trend_data.sort_values(by="Month_Year")
                    
                    bar_chart = px.bar(
                        trend_data, x="Month_Year", y="Cost", text="Cost",
                        title="Total Spending Month-over-Month",
                        labels={"Month_Year": "Month", "Cost": "Total Spent (₹)"}
                    )
                    bar_chart.update_traces(texttemplate='₹%{text:,.2f}', textposition='outside')
                    bar_chart.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
                    st.plotly_chart(bar_chart, use_container_width=True)
                else:
                    st.info("Log some expenses across different months to see your trends here!")
            # ---------------------------------
            st.write("---")
            with st.expander("🛠️ Manage Records"):
                st.write("Double-click cells to edit. To delete a record, check the box on the far left of the row and press 'Delete' on your keyboard.")
                
                visible_cols = ["Date", "Category", "Cost", "Details"]
                table_categories = [c for c in all_categories if c != "➕ Custom..."]
                
                live_table = st.data_editor(
                    records[visible_cols], 
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "Cost": st.column_config.NumberColumn("Cost (₹)", format="₹%.2f"),
                        "Date": st.column_config.DateColumn("Date"),
                        "Category": st.column_config.SelectboxColumn("Category", options=table_categories, required=True)
                    }
                )
                
                if st.button("Apply Changes"):
                    update_entire_sheet(current_user, sheet_client, live_table)
                    st.toast("Database updated!", icon="💾")
                    st.rerun()

if __name__ == "__main__":
    main()