import streamlit as st
import pandas as pd
import datetime
import json
import os
import random
import math
import qrcode
from PIL import Image
import io
import base64
from datetime import datetime as dt, timedelta

# --- 1. إعدادات وملفات البرنامج ---
DATA_DIR = "data"
EMPLOYEES_FILE = os.path.join(DATA_DIR, "employees.json")
ATTENDANCE_FILE = os.path.join(DATA_DIR, "attendance.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LEAVE_RECORDS_FILE = os.path.join(DATA_DIR, "leave_records.json")

# تأكد من وجود مجلد البيانات
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- 2. تحميل وحفظ البيانات ---
def load_data(file_path, default_data={}):
    """Loads data from a JSON file."""
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        with open(file_path, 'w') as f:
            json.dump(default_data, f, indent=4)
        return default_data
    with open(file_path, 'r') as f:
        return json.load(f)

def save_data(file_path, data):
    """Saves data to a JSON file."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# تحميل البيانات
employees_data = load_data(EMPLOYEES_FILE, {"employees": []})
for emp in employees_data["employees"]:
    if "sick_leave_balance" not in emp:
        emp["sick_leave_balance"] = 15.0
    if "annual_leave_balance" not in emp:
        emp["annual_leave_balance"] = 30.0
    if "comp_off_balance" not in emp:
        emp["comp_off_balance"] = 0.0
    if "public_holiday_comp_balance" not in emp:
        emp["public_holiday_comp_balance"] = 0.0
    if "redeemable_hours_balance" not in emp:
        emp["redeemable_hours_balance"] = 0.0
save_data(EMPLOYEES_FILE, employees_data)

settings_data = load_data(SETTINGS_FILE, {
    "attendance_cycle_start_day": 21,
    "standard_work_hours_per_day": 9,
    "current_theme": "cosmo",
    "last_overtime_transfer_date": "2000-01-01"
})
leave_records_data = load_data(LEAVE_RECORDS_FILE, {"records": []})

# --- 3. الدوال المساعدة ---
def generate_employee_color():
    r = random.randint(50, 200)
    g = random.randint(50, 200)
    b = random.randint(50, 200)
    return f"#{r:02x}{g:02x}{b:02x}"

def get_employee_by_code(employee_code):
    for emp in employees_data["employees"]:
        if emp["employee_code"] == employee_code:
            return emp
    return None

def calculate_duration_in_hours(start_time_str, end_time_str):
    try:
        FMT = '%H:%M:%S'
        tdelta = datetime.datetime.strptime(end_time_str, FMT) - datetime.datetime.strptime(start_time_str, FMT)
        return tdelta.total_seconds() / 3600
    except (ValueError, TypeError):
        return 0.0

def get_current_attendance_cycle():
    today = datetime.date.today()
    cycle_start_day = settings_data.get("attendance_cycle_start_day", 21)

    if today.day >= cycle_start_day:
        start_date = datetime.date(today.year, today.month, cycle_start_day)
        if today.month == 12:
            end_date = (datetime.date(today.year + 1, 1, cycle_start_day) - datetime.timedelta(days=1))
        else:
            end_date = (datetime.date(today.year, today.month + 1, cycle_start_day) - datetime.timedelta(days=1))
    else:
        if today.month == 1:
            start_date = datetime.date(today.year - 1, 12, cycle_start_day)
        else:
            start_date = datetime.date(today.year, today.month - 1, cycle_start_day)
        end_date = (datetime.date(today.year, today.month, cycle_start_day) - datetime.timedelta(days=1))
    
    return start_date, end_date

def get_previous_attendance_cycle():
    today = datetime.date.today()
    cycle_start_day = settings_data.get("attendance_cycle_start_day", 21)
    current_cycle_start, current_cycle_end = get_current_attendance_cycle()
    prev_cycle_end = current_cycle_start - datetime.timedelta(days=1)
    
    if prev_cycle_end.day >= cycle_start_day:
        prev_cycle_start = datetime.date(prev_cycle_end.year, prev_cycle_end.month, cycle_start_day)
    else:
        if prev_cycle_end.month == 1:
            prev_cycle_start = datetime.date(prev_cycle_end.year - 1, 12, cycle_start_day)
        else:
            prev_cycle_start = datetime.date(prev_cycle_end.year, prev_cycle_end.month - 1, cycle_start_day)
    return prev_cycle_start, prev_cycle_end

def calculate_employee_hours_and_overtime(employee_code, start_date, end_date):
    standard_hours_per_day = settings_data.get("standard_work_hours_per_day", 9)
    total_regular_hours = 0.0
    total_overtime_hours = 0.0
    
    attendance_records = load_data(ATTENDANCE_FILE, {})
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.isoformat()
        
        is_adjusted_attendance_day = False
        for rec in leave_records_data["records"]:
            if rec["employee_code"] == employee_code and \
               rec["date"] == date_str and \
               (rec["type"] == "Sick Leave (Attendance Adjustment)" or rec["type"] == "Weekly Off" or rec["type"] == "Redeem Hours"):
                is_adjusted_attendance_day = True
                break

        if date_str in attendance_records and employee_code in attendance_records[date_str]:
            record = attendance_records[date_str][employee_code]
            
            if record.get("check_in") and record.get("check_out"):
                worked_hours = record.get("total_hours_worked", 0.0)
                overtime_for_day = record.get("overtime_hours", 0.0)
                total_overtime_hours += overtime_for_day
                total_regular_hours += min(worked_hours, standard_hours_per_day) 
        
        current_date += datetime.timedelta(days=1)
    
    total_comp_off_added_days_in_cycle = 0
    total_public_holiday_worked_days_in_cycle = 0

    for rec in leave_records_data["records"]:
        record_date = datetime.date.fromisoformat(rec["date"])
        if rec["employee_code"] == employee_code and \
           start_date <= record_date <= end_date:
            if rec["type"] == "Comp Off" and rec["action"] == "Add":
                total_comp_off_added_days_in_cycle += 1
            elif rec["type"] == "Public Holiday (Worked)" and rec["action"] == "Add":
                total_public_holiday_worked_days_in_cycle += 1

    return {
        "total_regular_hours": round(total_regular_hours, 2),
        "total_overtime_hours": round(total_overtime_hours, 2),
        "total_comp_off_added_days": total_comp_off_added_days_in_cycle,
        "total_public_holiday_worked_days": total_public_holiday_worked_days_in_cycle
    }

def calculate_leave_activity_in_cycle(employee_code, start_date, end_date):
    activity = {
        "annual_leave_redeemed": 0,
        "comp_off_earned": 0,
        "comp_off_redeemed": 0,
        "public_holiday_comp_earned": 0,
        "sick_leave_used_normal": 0,
        "sick_leave_used_adjustment": 0,
        "weekly_off_marked": 0,
        "redeemed_hours_converted_to_days": 0,
        "comp_off_converted_to_hours": 0
    }

    for rec in leave_records_data["records"]:
        record_date = datetime.date.fromisoformat(rec["date"])
        if rec["employee_code"] == employee_code and \
           start_date <= record_date <= end_date:
            
            if rec["type"] == "Annual Leave" and rec["action"] == "Redeem":
                activity["annual_leave_redeemed"] += 1
            elif rec["type"] == "Comp Off" and rec["action"] == "Add":
                activity["comp_off_earned"] += 1
            elif rec["type"] == "Comp Off Redeemed" and rec["action"] == "Redeem":
                activity["comp_off_redeemed"] += 1
            elif rec["type"] == "Public Holiday (Worked)" and rec["action"] == "Add":
                activity["public_holiday_comp_earned"] += 1
            elif rec["type"] == "Sick Leave" and rec["action"] == "Redeem":
                activity["sick_leave_used_normal"] += 1
            elif rec["type"] == "Sick Leave (Attendance Adjustment)" and rec["action"] == "Adjust Attendance":
                activity["sick_leave_used_adjustment"] += 1
            elif rec["type"] == "Weekly Off" and rec["action"] == "Mark Weekly Off":
                activity["weekly_off_marked"] += 1
            elif rec["type"] == "Redeem Hours" and rec["action"] == "Redeem":
                activity["redeemed_hours_converted_to_days"] += rec.get("amount", 0)
            elif rec["type"] == "Comp Off Conversion" and rec["action"] == "Convert":
                activity["comp_off_converted_to_hours"] += rec.get("amount", 0)

    return activity

def record_attendance(employee_code):
    employee = get_employee_by_code(employee_code)
    if not employee:
        return False, "Employee not found!"

    today_str = datetime.date.today().isoformat()
    current_time_str = datetime.datetime.now().strftime("%H:%M:%S")

    attendance_records = load_data(ATTENDANCE_FILE, {})
    if today_str not in attendance_records:
        attendance_records[today_str] = {}

    if employee_code not in attendance_records[today_str]:
        attendance_records[today_str][employee_code] = {
            "name": employee["name"],
            "title": employee["title"],
            "check_in": current_time_str,
            "check_out": None,
            "breaks": [],
            "total_hours_worked": 0.0,
            "overtime_hours": 0.0
        }
        save_data(ATTENDANCE_FILE, attendance_records)
        return True, f"{employee['name']} Checked In at {current_time_str}"
    else:
        if attendance_records[today_str][employee_code]["check_out"] is None:
            attendance_records[today_str][employee_code]["check_out"] = current_time_str
            
            worked_hours = calculate_duration_in_hours(attendance_records[today_str][employee_code]["check_in"], current_time_str)
            attendance_records[today_str][employee_code]["total_hours_worked"] = round(worked_hours, 2)
            
            standard_hours = settings_data.get("standard_work_hours_per_day", 9)
            overtime_for_day = max(0, worked_hours - standard_hours)
            attendance_records[today_str][employee_code]["overtime_hours"] = round(overtime_for_day, 2)

            save_data(ATTENDANCE_FILE, attendance_records)
            return True, f"{employee['name']} Checked Out at {current_time_str}"
        else:
            return False, f"{employee['name']} already checked out today."

# --- 4. واجهة Streamlit ---
st.set_page_config(page_title="JewelAttend - YAS MALL", layout="wide")

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    .employee-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin-bottom: 0.5rem;
    }
    .status-success {
        color: #28a745;
        font-weight: bold;
    }
    .status-danger {
        color: #dc3545;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'page' not in st.session_state:
    st.session_state.page = 'main'
if 'scan_result' not in st.session_state:
    st.session_state.scan_result = None

# --- Main App ---
def main():
    # Header
    st.markdown('<div class="main-header"><h1>🏢 JewelAttend - YAS MALL</h1><p>Employee Attendance System</p></div>', unsafe_allow_html=True)
    
    # Sidebar navigation
    with st.sidebar:
        st.image("https://via.placeholder.com/150x150?text=JewelAttend", use_column_width=True)
        st.title("Navigation")
        
        if st.button("📋 Attendance", use_container_width=True):
            st.session_state.page = 'main'
        if st.button("👥 Employee Management", use_container_width=True):
            st.session_state.page = 'employees'
        if st.button("📊 Reports", use_container_width=True):
            st.session_state.page = 'reports'
        if st.button("🏖️ Leave Management", use_container_width=True):
            st.session_state.page = 'leaves'
        if st.button("⚙️ Settings", use_container_width=True):
            st.session_state.page = 'settings'
        
        st.divider()
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.info(f"🕐 {current_time}")
    
    # Page routing
    if st.session_state.page == 'main':
        attendance_page()
    elif st.session_state.page == 'employees':
        employee_management_page()
    elif st.session_state.page == 'reports':
        reports_page()
    elif st.session_state.page == 'leaves':
        leaves_management_page()
    elif st.session_state.page == 'settings':
        settings_page()

def attendance_page():
    st.header("📋 Attendance")
    
    col1, col2, col3 = st.columns([2, 1, 2])
    
    with col1:
        st.subheader("Scan Employee QR Code")
        employee_code = st.text_input("Enter Employee Code or Scan QR", placeholder="e.g., EMP001", key="scan_input")
        
        if st.button("🔍 Confirm Scan", type="primary", use_container_width=True):
            if employee_code:
                success, message = record_attendance(employee_code)
                if success:
                    st.success(f"✅ {message}")
                    st.balloons()
                else:
                    st.error(f"❌ {message}")
            else:
                st.warning("⚠️ Please enter an employee code")
    
    with col2:
        st.subheader("Quick Actions")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
        if st.button("📋 Today's Attendance", use_container_width=True):
            show_today_attendance()
    
    with col3:
        st.subheader("Recent Activity")
        # Show last 5 attendance records
        attendance_records = load_data(ATTENDANCE_FILE, {})
        today = datetime.date.today().isoformat()
        
        if today in attendance_records:
            st.write(f"**Today's Records:** {len(attendance_records[today])}")
            for emp_code, data in list(attendance_records[today].items())[:5]:
                status = "✅ Checked Out" if data.get('check_out') else "⏳ Checked In"
                st.info(f"**{data['name']}** - {status}")
        else:
            st.info("No attendance records for today yet")

def show_today_attendance():
    attendance_records = load_data(ATTENDANCE_FILE, {})
    today = datetime.date.today().isoformat()
    
    if today in attendance_records:
        data = []
        for emp_code, record in attendance_records[today].items():
            data.append({
                "Employee": record['name'],
                "Check In": record.get('check_in', 'N/A'),
                "Check Out": record.get('check_out', 'N/A'),
                "Hours Worked": record.get('total_hours_worked', 0),
                "Overtime": record.get('overtime_hours', 0)
            })
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No attendance records for today")

def employee_management_page():
    st.header("👥 Employee Management")
    
    tab1, tab2 = st.tabs(["📋 Employee List", "➕ Add Employee"])
    
    with tab1:
        if employees_data["employees"]:
            # Convert to DataFrame for better display
            df_employees = pd.DataFrame(employees_data["employees"])
            df_display = df_employees[['employee_code', 'name', 'title', 'annual_leave_balance', 'comp_off_balance', 
                                      'sick_leave_balance', 'redeemable_hours_balance']]
            df_display.columns = ['Code', 'Name', 'Title', 'Annual Leave', 'Comp Off', 'Sick Leave', 'Redeemable Hours']
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Employee actions
            col1, col2, col3 = st.columns(3)
            with col1:
                selected_employee = st.selectbox("Select Employee for Actions", 
                                                [f"{emp['name']} ({emp['employee_code']})" for emp in employees_data["employees"]])
            with col2:
                if st.button("🗑️ Delete Employee", type="secondary"):
                    if selected_employee:
                        code = selected_employee.split('(')[-1].strip(')')
                        if st.warning(f"Are you sure you want to delete {selected_employee}?"):
                            employees_data["employees"] = [emp for emp in employees_data["employees"] if emp["employee_code"] != code]
                            save_data(EMPLOYEES_FILE, employees_data)
                            st.success(f"Employee {selected_employee} deleted!")
                            st.rerun()
            with col3:
                if st.button("📱 Generate QR Code", type="primary"):
                    if selected_employee:
                        code = selected_employee.split('(')[-1].strip(')')
                        generate_qr_code(code)
        else:
            st.info("No employees found. Add an employee using the 'Add Employee' tab.")
    
    with tab2:
        with st.form("add_employee_form"):
            st.subheader("Add New Employee")
            
            col1, col2 = st.columns(2)
            with col1:
                emp_code = st.text_input("Employee Code *", placeholder="e.g., EMP001")
                emp_name = st.text_input("Employee Name *", placeholder="Full Name")
            with col2:
                emp_title = st.text_input("Job Title *", placeholder="e.g., Manager")
                color = st.color_picker("Pick a color for this employee", generate_employee_color())
            
            submitted = st.form_submit_button("➕ Add Employee", type="primary", use_container_width=True)
            
            if submitted:
                if not emp_code or not emp_name or not emp_title:
                    st.error("Please fill all required fields!")
                else:
                    # Check if employee code already exists
                    if any(emp["employee_code"] == emp_code for emp in employees_data["employees"]):
                        st.error(f"Employee code '{emp_code}' already exists!")
                    else:
                        new_employee = {
                            "name": emp_name,
                            "employee_code": emp_code,
                            "title": emp_title,
                            "color": color,
                            "sick_leave_balance": 15.0,
                            "annual_leave_balance": 30.0,
                            "comp_off_balance": 0.0,
                            "public_holiday_comp_balance": 0.0,
                            "redeemable_hours_balance": 0.0
                        }
                        employees_data["employees"].append(new_employee)
                        save_data(EMPLOYEES_FILE, employees_data)
                        st.success(f"✅ Employee '{emp_name}' added successfully!")
                        st.balloons()
                        st.rerun()

def generate_qr_code(employee_code):
    employee = get_employee_by_code(employee_code)
    if not employee:
        st.error("Employee not found!")
        return
    
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(employee_code)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for display
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    st.markdown(f"""
    <div style="text-align: center; padding: 20px;">
        <h3>QR Code for {employee['name']}</h3>
        <img src="data:image/png;base64,{img_str}" width="300">
        <p><strong>Employee Code:</strong> {employee_code}</p>
        <p><strong>Name:</strong> {employee['name']}</p>
        <p><strong>Title:</strong> {employee['title']}</p>
    </div>
    """, unsafe_allow_html=True)

def reports_page():
    st.header("📊 Reports & Overtime")
    
    start_date, end_date = get_current_attendance_cycle()
    st.info(f"📅 Current Attendance Cycle: **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**")
    
    if employees_data["employees"]:
        # Generate report data
        report_data = []
        for emp in employees_data["employees"]:
            calculated = calculate_employee_hours_and_overtime(emp["employee_code"], start_date, end_date)
            report_data.append({
                "Employee Code": emp["employee_code"],
                "Name": emp["name"],
                "Regular Hours": calculated["total_regular_hours"],
                "Overtime Hours": calculated["total_overtime_hours"],
                "Comp Off Earned": calculated["total_comp_off_added_days"],
                "Public Holiday Worked": calculated["total_public_holiday_worked_days"]
            })
        
        df_report = pd.DataFrame(report_data)
        st.dataframe(df_report, use_container_width=True, hide_index=True)
        
        # Export and actions
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔄 Refresh Report", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("📥 Export to CSV", use_container_width=True):
                csv = df_report.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv,
                    file_name=f"attendance_report_{datetime.date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        with col3:
            if st.button("🔄 Transfer Overtime", type="primary", use_container_width=True):
                if st.warning("Are you sure you want to transfer overtime hours to redeemable balance?"):
                    perform_overtime_transfer()
        
        # Leave Balances Summary
        st.subheader("📋 Leave Balances Summary")
        leave_data = []
        for emp in employees_data["employees"]:
            leave_activity = calculate_leave_activity_in_cycle(emp["employee_code"], start_date, end_date)
            leave_data.append({
                "Employee": emp["name"],
                "Annual Leave": emp.get("annual_leave_balance", 0),
                "Comp Off": emp.get("comp_off_balance", 0),
                "Sick Leave": emp.get("sick_leave_balance", 0),
                "Redeemable Hours": emp.get("redeemable_hours_balance", 0),
                "Used This Cycle": leave_activity["annual_leave_redeemed"] + leave_activity["sick_leave_used_normal"]
            })
        df_leave = pd.DataFrame(leave_data)
        st.dataframe(df_leave, use_container_width=True, hide_index=True)
    else:
        st.warning("No employees found to generate reports.")

def perform_overtime_transfer():
    last_transfer_date_str = settings_data.get("last_overtime_transfer_date", "2000-01-01")
    last_transfer_date = datetime.date.fromisoformat(last_transfer_date_str)
    standard_hours_per_day = settings_data.get("standard_work_hours_per_day", 9)
    
    attendance_records = load_data(ATTENDANCE_FILE, {})
    previous_cycle_start, previous_cycle_end = get_previous_attendance_cycle()

    if previous_cycle_end <= last_transfer_date:
        st.info("No new completed attendance cycles to transfer overtime from.")
        return

    start_date_for_transfer = last_transfer_date + datetime.timedelta(days=1)
    end_date_for_transfer = previous_cycle_end

    if start_date_for_transfer > end_date_for_transfer:
        st.info("No new completed attendance cycles to transfer overtime from.")
        return

    total_transferred_hours_global = 0.0
    updates_made = False

    for emp in employees_data["employees"]:
        employee_code = emp["employee_code"]
        total_overtime_to_transfer = 0.0
        
        current_date_to_check = start_date_for_transfer
        while current_date_to_check <= end_date_for_transfer:
            date_str = current_date_to_check.isoformat()
            
            if date_str in attendance_records and employee_code in attendance_records[date_str]:
                record = attendance_records[date_str][employee_code]
                if record.get("overtime_hours", 0) > 0:
                    total_overtime_to_transfer += record["overtime_hours"]
            
            current_date_to_check += datetime.timedelta(days=1)

        if total_overtime_to_transfer > 0:
            emp["redeemable_hours_balance"] += total_overtime_to_transfer
            total_transferred_hours_global += total_overtime_to_transfer
            updates_made = True

            new_record = {
                "employee_code": employee_code,
                "date": datetime.date.today().isoformat(),
                "type": "Overtime Transfer",
                "action": "Add",
                "notes": f"Transferred {round(total_overtime_to_transfer, 2)} hours from cycle ending {end_date_for_transfer.isoformat()}",
                "amount": round(total_overtime_to_transfer, 2)
            }
            leave_records_data["records"].append(new_record)
    
    if updates_made:
        save_data(EMPLOYEES_FILE, employees_data)
        save_data(LEAVE_RECORDS_FILE, leave_records_data)
        settings_data["last_overtime_transfer_date"] = end_date_for_transfer.isoformat()
        save_data(SETTINGS_FILE, settings_data)
        st.success(f"✅ Successfully transferred {round(total_transferred_hours_global, 2)} total overtime hours!")
        st.balloons()
    else:
        st.info("No new overtime hours found for transfer.")

def leaves_management_page():
    st.header("🏖️ Leave Management")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "➕ Add Leave", "🔄 Redeem Leave", "🤒 Sick Leave", "📅 Weekly Off", "🔄 Conversions"
    ])
    
    with tab1:
        st.subheader("Add Compensatory / Public Holiday Leave")
        
        if employees_data["employees"]:
            col1, col2 = st.columns(2)
            with col1:
                emp_select = st.selectbox("Select Employee", 
                                         [f"{emp['name']} ({emp['employee_code']})" for emp in employees_data["employees"]],
                                         key="add_leave_emp")
                leave_date = st.date_input("Date", datetime.date.today(), key="add_leave_date")
            with col2:
                leave_type = st.selectbox("Leave Type", ["Comp Off", "Public Holiday (Worked)"], key="add_leave_type")
                notes = st.text_input("Notes (Optional)", key="add_leave_notes")
            
            if st.button("➕ Add Leave", type="primary", use_container_width=True):
                if emp_select:
                    employee_code = emp_select.split('(')[-1].strip(')')
                    date_str = leave_date.isoformat()
                    
                    # Check for duplicates
                    duplicate = any(
                        rec["employee_code"] == employee_code and 
                        rec["date"] == date_str and 
                        rec["type"] == leave_type
                        for rec in leave_records_data["records"]
                    )
                    
                    if duplicate:
                        st.warning("⚠️ This record already exists!")
                    else:
                        employee = get_employee_by_code(employee_code)
                        new_record = {
                            "employee_code": employee_code,
                            "date": date_str,
                            "type": leave_type,
                            "action": "Add",
                            "notes": notes,
                            "amount": 1.0
                        }
                        leave_records_data["records"].append(new_record)
                        
                        if leave_type == "Comp Off":
                            employee["comp_off_balance"] += 1.0
                        elif leave_type == "Public Holiday (Worked)":
                            employee["public_holiday_comp_balance"] += 1.0
                        
                        save_data(LEAVE_RECORDS_FILE, leave_records_data)
                        save_data(EMPLOYEES_FILE, employees_data)
                        st.success(f"✅ {leave_type} added for {emp_select} on {leave_date}")
                        st.balloons()
        else:
            st.warning("No employees found. Please add employees first.")
    
    with tab2:
        st.subheader("Redeem Leave (Deduct from Balance)")
        
        if employees_data["employees"]:
            col1, col2 = st.columns(2)
            with col1:
                emp_select = st.selectbox("Select Employee", 
                                         [f"{emp['name']} ({emp['employee_code']})" for emp in employees_data["employees"]],
                                         key="redeem_emp")
                redeem_date = st.date_input("Date", datetime.date.today(), key="redeem_date")
                redeem_type = st.selectbox("Leave Type", ["Annual Leave", "Sick Leave", "Comp Off Redeemed", "Redeem Hours"], key="redeem_type")
            with col2:
                notes = st.text_input("Notes (Optional)", key="redeem_notes")
                hours = st.number_input("Hours to Redeem (if applicable)", min_value=0.0, step=0.5, key="redeem_hours")
            
            if st.button("🔄 Redeem Leave", type="primary", use_container_width=True):
                if emp_select:
                    employee_code = emp_select.split('(')[-1].strip(')')
                    employee = get_employee_by_code(employee_code)
                    date_str = redeem_date.isoformat()
                    
                    success = True
                    if redeem_type == "Redeem Hours" and hours > 0:
                        if employee.get("redeemable_hours_balance", 0) < hours:
                            st.warning(f"Insufficient redeemable hours. Balance: {employee.get('redeemable_hours_balance', 0)}")
                            success = False
                        else:
                            standard_hours_per_day = settings_data.get("standard_work_hours_per_day", 9)
                            amount_to_deduct = hours / standard_hours_per_day
                            employee["redeemable_hours_balance"] -= hours
                            message = f"{hours} hours redeemed"
                    else:
                        if redeem_type == "Annual Leave" and employee.get("annual_leave_balance", 0) < 1:
                            st.warning("Insufficient annual leave balance")
                            success = False
                        elif redeem_type == "Comp Off Redeemed" and employee.get("comp_off_balance", 0) < 1:
                            st.warning("Insufficient comp off balance")
                            success = False
                        elif redeem_type == "Sick Leave" and employee.get("sick_leave_balance", 0) < 1:
                            st.warning("Insufficient sick leave balance")
                            success = False
                        else:
                            if redeem_type == "Annual Leave":
                                employee["annual_leave_balance"] -= 1.0
                            elif redeem_type == "Comp Off Redeemed":
                                employee["comp_off_balance"] -= 1.0
                            elif redeem_type == "Sick Leave":
                                employee["sick_leave_balance"] -= 1.0
                            message = f"1 day of {redeem_type} redeemed"
                    
                    if success:
                        new_record = {
                            "employee_code": employee_code,
                            "date": date_str,
                            "type": redeem_type,
                            "action": "Redeem",
                            "notes": notes,
                            "amount": hours if redeem_type == "Redeem Hours" else 1.0
                        }
                        leave_records_data["records"].append(new_record)
                        save_data(LEAVE_RECORDS_FILE, leave_records_data)
                        save_data(EMPLOYEES_FILE, employees_data)
                        st.success(f"✅ {message} for {emp_select}")
        else:
            st.warning("No employees found.")
    
    with tab3:
        st.subheader("Register Sick Leave (Counts as Attendance)")
        
        if employees_data["employees"]:
            col1, col2 = st.columns(2)
            with col1:
                emp_select = st.selectbox("Select Employee", 
                                         [f"{emp['name']} ({emp['employee_code']})" for emp in employees_data["employees"]],
                                         key="sick_emp")
                sick_date = st.date_input("Date", datetime.date.today(), key="sick_date")
            with col2:
                sick_notes = st.text_input("Notes", key="sick_notes")
            
            if st.button("🤒 Register Sick Leave", type="primary", use_container_width=True):
                if emp_select:
                    employee_code = emp_select.split('(')[-1].strip(')')
                    employee = get_employee_by_code(employee_code)
                    date_str = sick_date.isoformat()
                    
                    if employee.get("sick_leave_balance", 0) < 1:
                        st.warning(f"Insufficient sick leave balance. Balance: {employee.get('sick_leave_balance', 0)}")
                    else:
                        new_record = {
                            "employee_code": employee_code,
                            "date": date_str,
                            "type": "Sick Leave (Attendance Adjustment)",
                            "action": "Adjust Attendance",
                            "notes": sick_notes,
                            "amount": 1.0
                        }
                        leave_records_data["records"].append(new_record)
                        employee["sick_leave_balance"] -= 1.0
                        save_data(LEAVE_RECORDS_FILE, leave_records_data)
                        save_data(EMPLOYEES_FILE, employees_data)
                        st.success(f"✅ Sick leave registered for {emp_select}")
        else:
            st.warning("No employees found.")
    
    with tab4:
        st.subheader("Mark Weekly Off Day")
        
        if employees_data["employees"]:
            col1, col2 = st.columns(2)
            with col1:
                emp_select = st.selectbox("Select Employee", 
                                         [f"{emp['name']} ({emp['employee_code']})" for emp in employees_data["employees"]],
                                         key="wo_emp")
                wo_date = st.date_input("Date", datetime.date.today(), key="wo_date")
            with col2:
                wo_notes = st.text_input("Notes", key="wo_notes")
            
            if st.button("📅 Mark Weekly Off", type="primary", use_container_width=True):
                if emp_select:
                    employee_code = emp_select.split('(')[-1].strip(')')
                    date_str = wo_date.isoformat()
                    
                    new_record = {
                        "employee_code": employee_code,
                        "date": date_str,
                        "type": "Weekly Off",
                        "action": "Mark Weekly Off",
                        "notes": wo_notes,
                        "amount": 1.0
                    }
                    leave_records_data["records"].append(new_record)
                    save_data(LEAVE_RECORDS_FILE, leave_records_data)
                    st.success(f"✅ Weekly Off marked for {emp_select}")
        else:
            st.warning("No employees found.")
    
    with tab5:
        st.subheader("Convert Comp Off to Redeemable Hours")
        
        if employees_data["employees"]:
            col1, col2 = st.columns(2)
            with col1:
                emp_select = st.selectbox("Select Employee", 
                                         [f"{emp['name']} ({emp['employee_code']})" for emp in employees_data["employees"]],
                                         key="conv_emp")
                conv_date = st.date_input("Date", datetime.date.today(), key="conv_date")
            with col2:
                conv_notes = st.text_input("Notes", key="conv_notes")
            
            if st.button("🔄 Convert Comp Off to Hours", type="primary", use_container_width=True):
                if emp_select:
                    employee_code = emp_select.split('(')[-1].strip(')')
                    employee = get_employee_by_code(employee_code)
                    
                    if employee.get("comp_off_balance", 0) < 1.0:
                        st.warning(f"Insufficient Comp Off balance. Balance: {employee.get('comp_off_balance', 0)}")
                    else:
                        standard_hours_per_day = settings_data.get("standard_work_hours_per_day", 9)
                        employee["comp_off_balance"] -= 1.0
                        employee["redeemable_hours_balance"] += standard_hours_per_day
                        
                        new_record = {
                            "employee_code": employee_code,
                            "date": conv_date.isoformat(),
                            "type": "Comp Off Conversion",
                            "action": "Convert",
                            "notes": conv_notes,
                            "amount": standard_hours_per_day
                        }
                        leave_records_data["records"].append(new_record)
                        save_data(EMPLOYEES_FILE, employees_data)
                        save_data(LEAVE_RECORDS_FILE, leave_records_data)
                        st.success(f"✅ 1 Comp Off day converted to {standard_hours_per_day} hours for {emp_select}")
        else:
            st.warning("No employees found.")

def settings_page():
    st.header("⚙️ Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Attendance Settings")
        cycle_day = st.number_input("Attendance Cycle Start Day", min_value=1, max_value=31, 
                                   value=settings_data.get("attendance_cycle_start_day", 21))
        standard_hours = st.number_input("Standard Work Hours/Day", min_value=1.0, max_value=24.0, 
                                        value=settings_data.get("standard_work_hours_per_day", 9.0))
        
        if st.button("💾 Save Settings", type="primary", use_container_width=True):
            settings_data["attendance_cycle_start_day"] = cycle_day
            settings_data["standard_work_hours_per_day"] = standard_hours
            save_data(SETTINGS_FILE, settings_data)
            st.success("✅ Settings saved successfully!")
    
    with col2:
        st.subheader("System Information")
        st.info(f"📁 Data Directory: {DATA_DIR}")
        st.info(f"👥 Total Employees: {len(employees_data['employees'])}")
        st.info(f"📋 Total Leave Records: {len(leave_records_data['records'])}")
        
        # Display last overtime transfer
        last_transfer = settings_data.get("last_overtime_transfer_date", "Never")
        st.info(f"🔄 Last Overtime Transfer: {last_transfer}")
        
        if st.button("🔄 Reset All Data", type="secondary", use_container_width=True):
            if st.warning("⚠️ This will delete ALL data. Are you sure?"):
                # Backup data
                backup_dir = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(backup_dir, exist_ok=True)
                for file in [EMPLOYEES_FILE, ATTENDANCE_FILE, SETTINGS_FILE, LEAVE_RECORDS_FILE]:
                    if os.path.exists(file):
                        os.rename(file, os.path.join(backup_dir, os.path.basename(file)))
                st.success(f"All data has been reset. Backup created in '{backup_dir}'")
                st.rerun()

# --- Run the app ---
if __name__ == "__main__":
    main()