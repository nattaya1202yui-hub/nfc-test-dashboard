import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import glob
import re

st.set_page_config(page_title="NFC Test Bench Multi-Model Dashboard", layout="wide")

# ==========================================
# ฟังก์ชันสำหรับอ่านไฟล์ HTML และอัปเดต CSV
# ==========================================
def parse_and_update_csv():
    data = []
    for file_path in glob.glob("*_Test_Report_*.html"):
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
            
            meta_div = soup.find("div", class_="meta")
            meta_text = meta_div.text if meta_div else ""
            
            # ดึง 2D Scan
            scan_2d = ""
            match_2d = re.search(r'2D Scan:\s*<strong>(.*?)</strong>', str(meta_div))
            if match_2d:
                scan_2d = match_2d.group(1).strip()
                
            # ระบุ Model จาก 4 หลักแรกของ 2D Scan
            model_name = "Unknown Model"
            if scan_2d.startswith("8876"):
                model_name = "NFC RH"
            elif scan_2d.startswith("8875"):
                model_name = "NFC LH"
            elif scan_2d.startswith("8878"):
                model_name = "NON-NFC RH"
            elif scan_2d.startswith("8877"):
                model_name = "NON-NFC LH"
                
            # ดึง Timestamp
            gen_time = ""
            match_time = re.search(r'Generated:\s*([\d\s:-]+)', meta_text)
            if match_time:
                gen_time = match_time.group(1).strip()
                
            # ดึงผลทดสอบแต่ละ Test Case
            for table in soup.find_all("table"):
                tbody = table.find("tbody")
                if tbody:
                    for row in tbody.find_all("tr"):
                        cols = row.find_all("td")
                        if len(cols) >= 9:
                            tcid = cols[1].text.strip()
                            tc_name = cols[2].text.strip()
                            expected = cols[5].text.strip()
                            observed = cols[7].text.strip()
                            status = cols[8].text.strip()
                            
                            data.append({
                                "File": file_path,
                                "2D_Scan": scan_2d if scan_2d else file_path,
                                "Model": model_name,
                                "Timestamp": gen_time,
                                "Test ID": tcid,
                                "Test Name": tc_name,
                                "Expected (Spec)": expected,
                                "Observed Result": observed,
                                "Status": status
                            })

    if data:
        df_new = pd.DataFrame(data)
        df_new.to_csv("test_summary_dashboard.csv", index=False, encoding="utf-8-sig")

# ==========================================
# Header & ปุ่ม Refresh
# ==========================================
header_col1, header_col2 = st.columns([6, 1])
with header_col1:
    st.title("📊 Smart BU Test Bench Analysis Dashboard")
with header_col2:
    st.write("")
    if st.button("🔄 Refresh Data", use_container_width=True):
        with st.spinner("กำลังอ่านและประมวลผลไฟล์รายงานใหม่..."):
            parse_and_update_csv() # สั่งแปลงไฟล์ HTML เป็น CSV ใหม่ทันที
            st.cache_data.clear()   # ล้าง Cache
            st.rerun()              # รีโหลดหน้าจอใหม่

@st.cache_data
def load_data():
    df = pd.read_csv("test_summary_dashboard.csv")
    
    # Parse General Spec Min / Max
    def parse_spec(spec_str):
        match_range = re.search(r'([\d\.]+)\s*-\s*([\d\.]+)', str(spec_str))
        if match_range:
            return float(match_range.group(1)), float(match_range.group(2))
        match_gt = re.search(r'>\s*([\d\.]+)', str(spec_str))
        if match_gt:
            return float(match_gt.group(1)), None
        match_eq = re.search(r'=\s*([\d\.]+)', str(spec_str))
        if match_eq:
            val = float(match_eq.group(1))
            return val, val
        return None, None

    # Parse General Numeric Observed Value
    def parse_obs(obs_str):
        match = re.search(r'[\w\+]+\s*=\s*([\d\.]+)', str(obs_str))
        if match:
            return float(match.group(1))
        match_num = re.search(r'([\d\.]+)', str(obs_str))
        if match_num:
            return float(match_num.group(1))
        return None

    specs = df['Expected (Spec)'].apply(parse_spec)
    df['Spec_Min'] = [s[0] for s in specs]
    df['Spec_Max'] = [s[1] for s in specs]
    df['Observed_Value'] = df['Observed Result'].apply(parse_obs)
    
    # ฟังก์ชันแยกค่า TC_MOTOR_01
    def parse_motor_results(row):
        obs = str(row['Observed Result'])
        exp = str(row['Expected (Spec)'])
        
        v_obs = re.search(r'MotorVoltage\s*=\s*([\d\.]+)', obs)
        c_obs = re.search(r'MotorCurrent\s*=\s*([\d\.]+)', obs)
        e_obs = re.search(r'MotorLoadError\s*=\s*([\d\.]+)', obs)
        
        v_spec = re.search(r'MotorVoltage\s*>\s*([\d\.]+)', exp)
        c_spec = re.search(r'MotorCurrent\s*>\s*([\d\.]+)', exp)
        e_spec = re.search(r'MotorLoadError\s*=\s*([\d\.]+)', exp)
        
        return pd.Series({
            'MotorVoltage_Obs': float(v_obs.group(1)) if v_obs else None,
            'MotorCurrent_Obs': float(c_obs.group(1)) if c_obs else None,
            'MotorLoadError_Obs': float(e_obs.group(1)) if e_obs else None,
            'MotorVoltage_Min': float(v_spec.group(1)) if v_spec else None,
            'MotorCurrent_Min': float(c_spec.group(1)) if c_spec else None,
            'MotorLoadError_Spec': float(e_spec.group(1)) if e_spec else None,
        })

    motor_df = df.apply(parse_motor_results, axis=1)
    df = pd.concat([df, motor_df], axis=1)
    
    return df

df = load_data()

# Sidebar: เลือก Model
st.sidebar.header("🎯 Model Selection")
model_list = sorted(df['Model'].unique())
selected_model = st.sidebar.selectbox("Select Model:", model_list)

# กรองข้อมูลตาม Model
df_model = df[df['Model'] == selected_model].copy()

# สรุปภาพรวม
st.subheader(f"🏷️ Overview for Model: {selected_model}")
total_boards = df_model['2D_Scan'].nunique()
total_tests = len(df_model)
total_pass = (df_model['Status'] == 'PASS').sum()
total_fail = (df_model['Status'] == 'FAIL').sum()
yield_rate = (total_pass / total_tests * 100) if total_tests > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Tested Boards", total_boards)
col2.metric("Total Pass Test Items", total_pass)
col3.metric("Total Fail Test Items", total_fail)
col4.metric("Overall Yield Rate", f"{yield_rate:.1f}%")

st.markdown("---")

# แสดงผลทุก Test Case
st.subheader(f"📈 All Test Cases Trend Analysis ({selected_model})")

test_cases = df_model['Test ID'].unique()

for tcid in test_cases:
    df_tc = df_model[df_model['Test ID'] == tcid].copy()
    tc_name = df_tc['Test Name'].iloc[0] if not df_tc.empty else ""
    
    with st.expander(f"🔹 {tcid} — {tc_name}", expanded=True):
        
        # กรณีพิเศษ: TC_MOTOR_01 (แยก 3 กราฟ)
        if tcid == "TC_MOTOR_01":
            st.markdown("#### ⚡ Motor Parameters Trend Analysis")
            
            # 1. Motor Voltage
            fig_v = go.Figure()
            fig_v.add_trace(go.Scatter(
                x=df_tc['2D_Scan'].astype(str), y=df_tc['MotorVoltage_Obs'],
                mode='lines+markers', name='MotorVoltage (mV)', marker=dict(color='blue', size=8)
            ))
            v_min = df_tc['MotorVoltage_Min'].iloc[0]
            if pd.notnull(v_min):
                fig_v.add_hline(y=v_min, line_dash="dash", line_color="red", annotation_text=f"Spec Min: > {v_min} mV")
            fig_v.update_layout(height=260, title="1. Motor Voltage (mV)", yaxis_title="Voltage (mV)", xaxis=dict(type='category'), margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_v, use_container_width=True, key=f"chart_{tcid}_voltage")

            # 2. Motor Current
            fig_c = go.Figure()
            fig_c.add_trace(go.Scatter(
                x=df_tc['2D_Scan'].astype(str), y=df_tc['MotorCurrent_Obs'],
                mode='lines+markers', name='MotorCurrent (mA)', marker=dict(color='orange', size=8)
            ))
            c_min = df_tc['MotorCurrent_Min'].iloc[0]
            if pd.notnull(c_min):
                fig_c.add_hline(y=c_min, line_dash="dash", line_color="red", annotation_text=f"Spec Min: > {c_min} mA")
            fig_c.update_layout(height=260, title="2. Motor Current (mA)", yaxis_title="Current (mA)", xaxis=dict(type='category'), margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_c, use_container_width=True, key=f"chart_{tcid}_current")

            # 3. Motor Load Error
            fig_e = go.Figure()
            fig_e.add_trace(go.Scatter(
                x=df_tc['2D_Scan'].astype(str), y=df_tc['MotorLoadError_Obs'],
                mode='lines+markers', name='MotorLoadError', marker=dict(color='purple', size=8)
            ))
            e_spec = df_tc['MotorLoadError_Spec'].iloc[0]
            if pd.notnull(e_spec):
                fig_e.add_hline(y=e_spec, line_dash="dash", line_color="red", annotation_text=f"Spec Limit: = {e_spec}")
            fig_e.update_layout(height=260, title="3. Motor Load Error (0 = Pass)", yaxis_title="Error Status", xaxis=dict(type='category'), margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_e, use_container_width=True, key=f"chart_{tcid}_error")

        # กรณี Test Case ทั่วไป
        else:
            if not df_tc['Observed_Value'].dropna().empty:
                fig = go.Figure()

                fig.add_trace(go.Scatter(
                    x=df_tc['2D_Scan'].astype(str), 
                    y=df_tc['Observed_Value'],
                    mode='lines+markers',
                    name='Observed Value',
                    marker=dict(color='blue', size=8),
                    hovertext=df_tc['Observed Result']
                ))

                spec_min = df_tc['Spec_Min'].iloc[0]
                if pd.notnull(spec_min):
                    fig.add_hline(y=spec_min, line_dash="dash", line_color="red", annotation_text=f"Spec Min: {spec_min}")

                spec_max = df_tc['Spec_Max'].iloc[0]
                if pd.notnull(spec_max):
                    fig.add_hline(y=spec_max, line_dash="dash", line_color="red", annotation_text=f"Spec Max: {spec_max}")

                fig.update_layout(
                    height=320,
                    xaxis_title="2D Scan (Serial Number)",
                    yaxis_title="Measured Value",
                    hovermode="x unified",
                    margin=dict(l=20, r=20, t=30, b=20),
                    xaxis=dict(type='category')
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{tcid}")
            else:
                st.info("รายการนี้เป็นค่าสถานะ Pass/Fail ไม่มีค่าวัดเชิงตัวเลข")
            
        st.dataframe(df_tc[['2D_Scan', 'Timestamp', 'Expected (Spec)', 'Observed Result', 'Status']], use_container_width=True)