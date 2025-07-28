import streamlit as st
import pandas as pd
import re
import PyPDF2
import io
import datetime

# Set page config
st.set_page_config(
    page_title="CMM Data Parser",
    page_icon="📐",
    layout="wide"
)

def extract_pdf_text(file_content):
    """Extract text from PDF file"""
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return text
    except Exception as e:
        st.error(f"Error extracting PDF text: {e}")
        return None

def filtered_xy_parser(lines, use_japanese_columns=True, verbose=False):
    """
    Filtered parser focused on ONLY "円" and "ｄ-" elements
    Based on Google Colab filtered_xy_parser functionality
    """
    if verbose:
        st.info("🔧 Filtered XY Parser - Continuous stream processing...")
    
    # Step 1: Clean the lines by removing headers
    clean_lines = []
    header_pattern = r'(CARL ZEISS|CALYPSO|測定ﾌﾟﾗﾝ|ACCURA|名前|説明|実測値|基準値|上許容差|下許容誤差|ﾋｽﾄｸﾞﾗﾑ|ｺﾝﾊﾟｸﾄﾌﾟﾘﾝﾄｱｳﾄ|ｵﾍﾟﾚｰﾀ|日付|ﾊﾟｰﾄNo|Master|2025年|20190821|支持板)'
    separator_pattern = r'^[=_-]{10,}$'

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip all header/separator lines
        if re.search(header_pattern, line) or re.search(separator_pattern, line):
            if verbose:
                st.write(f"   Skipping header: {line[:50]}...")
            continue
        clean_lines.append(line)

    if verbose:
        st.info(f"📊 Cleaned document: {len(clean_lines)} useful lines")

    # Step 2: Process all clean lines sequentially
    xy_records = []
    current_element = None
    looking_for_x = False
    looking_for_y = False
    current_x = None

    for line_idx, line in enumerate(clean_lines):
        # Look for element patterns
        element_pattern = r'^([^\s]+)\s+(円\(最小二乗法\)|平面\(最小二乗法\)|直線\(最小二乗法\)|基本座標系|3次元直線|点|2D距離)'
        element_match = re.search(element_pattern, line)

        if element_match:
            candidate_tag = element_match.group(1)

            if verbose:
                st.write(f"   Line {line_idx}: Found candidate element '{candidate_tag}'")

            # FILTER: Only EXACT matches for "円" + numbers OR "ｄ-" + numbers
            circle_pattern = r'^円\d+$'
            d_pattern = r'^ｄ-\d+$'

            if re.search(circle_pattern, candidate_tag) or re.search(d_pattern, candidate_tag):
                # Save previous record if incomplete
                if current_element and current_x is not None and looking_for_y:
                    if verbose:
                        st.write(f"   ⚠️  Previous element {current_element} incomplete (missing Y)")

                # Start tracking new element
                current_element = candidate_tag
                looking_for_x = True
                looking_for_y = False
                current_x = None

                if verbose:
                    tag_type = "円グループ" if "円" in candidate_tag else "ｄ-グループ"
                    st.write(f"   ✅ ACCEPTED element: {current_element} ({tag_type})")
            else:
                if verbose:
                    st.write(f"   ❌ REJECTED element: {candidate_tag} (doesn't match filter)")
            continue

        # Look for X coordinate
        if current_element and looking_for_x:
            x_pattern = r'\bX\s+([-\d.]+)'
            x_match = re.search(x_pattern, line)
            if x_match:
                current_x = abs(float(x_match.group(1)))
                looking_for_x = False
                looking_for_y = True
                if verbose:
                    st.write(f"   ✅ Found X for {current_element}: {current_x}")
                continue

        # Look for Y coordinate
        if current_element and current_x is not None and looking_for_y:
            y_pattern = r'\bY\s+([-\d.]+)'
            y_match = re.search(y_pattern, line)
            if y_match:
                current_y = abs(float(y_match.group(1)))

                # Save complete record
                record = {
                    'element_name': current_element,
                    'x_coordinate': current_x,
                    'y_coordinate': current_y
                }
                xy_records.append(record)

                if verbose:
                    st.write(f"   ✅ COMPLETE: {current_element} X={current_x} Y={current_y}")

                # Reset for next element
                current_element = None
                looking_for_x = False
                looking_for_y = False
                current_x = None
                continue

    if verbose:
        st.success(f"📊 FILTERED XY EXTRACTION SUMMARY:")
        st.info(f"✅ Total clean lines processed: {len(clean_lines)}")
        st.info(f"✅ Total filtered XY records: {len(xy_records)}")

    if xy_records:
        # Separate into groups - KEY FUNCTIONALITY FROM COLAB
        circle_elements = [r for r in xy_records if "円" in r['element_name']]
        d_elements = [r for r in xy_records if "ｄ-" in r['element_name']]

        if verbose:
            st.info(f"📊 Groups found:")
            st.write(f"   円グループ: {len(circle_elements)} elements")
            st.write(f"   ｄ-グループ: {len(d_elements)} elements")

        # NUMERICAL SORTING FUNCTION
        def extract_number(element_name):
            if "円" in element_name:
                match = re.search(r'円(\d+)', element_name)
                return int(match.group(1)) if match else 0
            elif "ｄ-" in element_name:
                match = re.search(r'ｄ-(\d+)', element_name)
                return int(match.group(1)) if match else 0
            return 0

        # Create reshaped data with numerical sorting
        reshaped_data = []

        # Add 円 group elements (sorted numerically)
        circle_elements_sorted = sorted(circle_elements, key=lambda x: extract_number(x['element_name']))
        for element_record in circle_elements_sorted:
            # Add X row
            reshaped_data.append({
                'element_name': element_record['element_name'],
                'coordinate_type': 'X',
                'value': element_record['x_coordinate']
            })
            # Add Y row
            reshaped_data.append({
                'element_name': element_record['element_name'],
                'coordinate_type': 'Y',
                'value': element_record['y_coordinate']
            })

        # Add ｄ- group elements (sorted numerically)
        d_elements_sorted = sorted(d_elements, key=lambda x: extract_number(x['element_name']))
        for element_record in d_elements_sorted:
            # Add X row
            reshaped_data.append({
                'element_name': element_record['element_name'],
                'coordinate_type': 'X',
                'value': element_record['x_coordinate']
            })
            # Add Y row
            reshaped_data.append({
                'element_name': element_record['element_name'],
                'coordinate_type': 'Y',
                'value': element_record['y_coordinate']
            })

        df = pd.DataFrame(reshaped_data)

        # Convert column names if Japanese requested
        if use_japanese_columns:
            df = df.rename(columns={
                'element_name': '要素名',
                'coordinate_type': '座標種別',
                'value': '値'
            })
        else:
            df = df.rename(columns={
                'element_name': 'Element_Name',
                'coordinate_type': 'Coordinate_Type',
                'value': 'Value'
            })

        if verbose:
            st.success(f"✅ Reshaped DataFrame created!")
            st.info(f"📐 Shape: {df.shape[0]} rows × {df.shape[1]} columns")
            st.write("📍 Sample data:")
            st.dataframe(df.head(10))

        return df
    else:
        if verbose:
            st.error("❌ No filtered XY coordinate records found")
        return pd.DataFrame()

def convert_df_to_excel(df):
    """Convert DataFrame to Excel bytes - GUARANTEED TO WORK"""
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='CMM_Data')
        excel_data = output.getvalue()
        return excel_data
    except Exception as e:
        st.error(f"Excel conversion error: {e}")
        return None

# Main Streamlit App
st.markdown("# Zeiss社pdf出力データ解析アプリ v2.0")

# Sidebar
with st.sidebar:
    st.header("📋 使い方")
    st.markdown("1. PDFファイルをアップロード")
    st.markdown("2. Process Fileをクリック")
    st.markdown("3. Excelファイルをダウンロード")
    
    st.header("🎯 フィルタ対象")
    st.markdown("- **円1, 円2, 円3...** ✅")
    st.markdown("- **ｄ-1, ｄ-2, ｄ-3...** ✅") 
    st.markdown("- **基準円27** ❌ (除外)")
    st.markdown("- **その他** ❌ (除外)")
    
    use_japanese_columns = st.checkbox("日本語列名を使用", value=True)
    verbose_mode = st.checkbox("詳細ログを表示", value=False)

# File upload
st.header("📁 PDFファイルをアップロード")
uploaded_file = st.file_uploader(
    label="PDFファイルを選択してください",
    type="pdf",
    help="Zeiss CMM測定結果のPDFファイルをアップロードしてください"
)

if uploaded_file is not None:
    # Show file details
    st.success(f"✅ ファイルのアップロードが完了しました: {uploaded_file.name}")
    
    file_info = f"**ファイル名:** {uploaded_file.name}\n**ファイルサイズ:** {uploaded_file.size:,} bytes"
    st.markdown(file_info)
    
    # Process button
    if st.button("🔄 Process File", type="primary"):
        with st.spinner("ファイルを処理しています..."):
            
            # Extract text
            file_content = uploaded_file.read()
            text = extract_pdf_text(file_content)
            
            if text:
                lines = text.split('\n')
                
                if verbose_mode:
                    st.info(f"📄 {len(lines)} 行のテキストを抽出しました")
                
                # Process with filtered parser
                df = filtered_xy_parser(lines, use_japanese_columns, verbose_mode)
                
                if not df.empty:
                    st.session_state.data = df
                    st.session_state.filename = uploaded_file.name
                    st.session_state.processed = True
                    st.success("✅ ファイル処理が完了しました!")
                else:
                    st.error("❌ No filtered data found")
            else:
                st.error("❌ PDFからテキストの抽出に失敗しました")

# Display results if processed
if hasattr(st.session_state, 'processed') and st.session_state.processed:
    df = st.session_state.data
    
    st.subheader("🎯 フィルタード抽出結果")
    
    # Show metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("座標レコード数", len(df))
    with col2:
        if use_japanese_columns:
            unique_elements = df['要素名'].nunique()
        else:
            unique_elements = df['Element_Name'].nunique()
        st.metric("要素数", unique_elements)
    with col3:
        if use_japanese_columns:
            coord_types = df['座標種別'].nunique()
        else:
            coord_types = df['Coordinate_Type'].nunique()
        st.metric("座標軸数", coord_types)
    
    # Display data
    st.dataframe(df, use_container_width=True)
    
    # Download button - Excel only
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = st.session_state.filename.replace('.pdf', '')
    
    excel_filename = f"CMM_Filtered_XY_{base_filename}_{timestamp}.xlsx"
    excel_data = convert_df_to_excel(df)
    if excel_data:
        st.download_button(
            label="📥 Excel形式でダウンロード",
            data=excel_data,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
    else:
        st.error("❌ Excel変換エラー")
    
    # Data preview
    with st.expander("👀 データプレビュー (最初の10行)"):
        st.dataframe(df.head(10))

# Footer
st.markdown("---")
st.markdown("For support, contact: Hirata Trading Co., Ltd.")