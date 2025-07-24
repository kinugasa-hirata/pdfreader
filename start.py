import streamlit as st
import pandas as pd
import re
import PyPDF2
import io
from typing import Dict, List, Any
import numpy as np
import datetime
import base64

# Set page config - MUST be first Streamlit command
st.set_page_config(
    page_title="CMM データパーサー",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

def ensure_japanese_text(text):
    """Ensure text is properly encoded for Japanese characters"""
    if isinstance(text, str):
        try:
            # Test if text can be encoded/decoded properly
            text.encode('utf-8').decode('utf-8')
            return text
        except UnicodeError:
            # If there's an encoding issue, try to fix it
            return text.encode('utf-8', errors='replace').decode('utf-8')
    return str(text)

def convert_df_to_csv(df, encoding='utf-8-sig'):
    """Convert DataFrame to CSV string with proper Japanese encoding"""
    try:
        # Try the specified encoding first
        csv_string = df.to_csv(index=False, encoding=encoding, errors='replace')
        return csv_string
    except UnicodeEncodeError:
        try:
            # Fallback to UTF-8 without BOM
            csv_string = df.to_csv(index=False, encoding='utf-8', errors='replace')
            return csv_string
        except:
            # Final fallback to Shift-JIS for Japanese systems
            csv_string = df.to_csv(index=False, encoding='shift_jis', errors='replace')
            return csv_string

class CMMDataParser:
    def __init__(self):
        self.measurement_data = []
        self.coordinate_system_data = {}
        self.reference_elements = {}
        
    def convert_to_absolute(self, value):
        """Convert numerical value to absolute value"""
        try:
            if isinstance(value, (int, float)):
                return abs(value)
            elif isinstance(value, str):
                try:
                    num_value = float(value)
                    return abs(num_value)
                except ValueError:
                    return value
            else:
                return value
        except:
            return value
        
    def extract_pdf_text(self, file_content):
        """Extract text from PDF file with proper Japanese encoding"""
        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                # Ensure Japanese text is properly handled
                if page_text:
                    page_text = ensure_japanese_text(page_text)
                    text += page_text + "\n"
            
            return text
        except Exception as e:
            st.error(f"PDFテキスト抽出エラー: {e}")
            return None
    
    def parse_measurement_line(self, line):
        """Parse a single measurement line to extract values"""
        patterns = {
            'circle': r'(円\d+|基準円\d+)\s+円\(最小二乗法\)\s+点数\s+\((\d+)\)\s+(内側|外側)?',
            'plane': r'(平面\d+|.*平面)\s+平面\(最小二乗法\)\s+点数\s+\((\d+)\)',
            'line': r'(.*線)\s+直線\(最小二乗法\)\s+点数\s+\((\d+)\)',
            'coordinate_value': r'([XYZ]-値_.*?|[XYZ])\s+([XYZ])\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)',
            'diameter': r'D\s+([\d.]+)\s+([\d.]+)',
            'statistics': r'S=\s+([\d.]+)\s+Min=\([^)]+\)\s+([-\d.]+)\s+Max=\([^)]+\)\s+([-\d.]+)\s+形状=\s+([\d.]+)'
        }
        
        result = {}
        
        for pattern_name, pattern in patterns.items():
            match = re.search(pattern, line)
            if match:
                result['type'] = pattern_name
                result['match'] = match
                break
                
        return result if result else None
    
    def parse_cmm_data(self, text):
        """Parse the entire CMM measurement text"""
        lines = text.split('\n')
        current_element = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            parsed_line = self.parse_measurement_line(line)
            
            if parsed_line:
                if parsed_line['type'] in ['circle', 'plane', 'line']:
                    if current_element:
                        self.measurement_data.append(current_element)
                    
                    current_element = {
                        'name': parsed_line['match'].group(1),
                        'type': parsed_line['type'],
                        'point_count': int(parsed_line['match'].group(2)) if len(parsed_line['match'].groups()) >= 2 else None,
                        'side': parsed_line['match'].group(3) if len(parsed_line['match'].groups()) >= 3 else None,
                        'coordinates': {},
                        'statistics': {},
                        'tolerances': {}
                    }
                
                elif parsed_line['type'] == 'coordinate_value' and current_element:
                    match = parsed_line['match']
                    coord_name = match.group(1)
                    coord_axis = match.group(2)
                    measured_value = self.convert_to_absolute(float(match.group(3)))
                    reference_value = self.convert_to_absolute(float(match.group(4)))
                    upper_tolerance = self.convert_to_absolute(float(match.group(5)))
                    lower_tolerance = self.convert_to_absolute(float(match.group(6)))
                    deviation = self.convert_to_absolute(float(match.group(7)))
                    
                    current_element['coordinates'][coord_name] = {
                        'axis': coord_axis,
                        'measured': measured_value,
                        'reference': reference_value,
                        'upper_tol': upper_tolerance,
                        'lower_tol': lower_tolerance,
                        'deviation': deviation
                    }
                
                elif parsed_line['type'] == 'diameter' and current_element:
                    match = parsed_line['match']
                    current_element['diameter'] = {
                        'measured': self.convert_to_absolute(float(match.group(1))),
                        'reference': self.convert_to_absolute(float(match.group(2)))
                    }
                
                elif parsed_line['type'] == 'statistics' and current_element:
                    match = parsed_line['match']
                    current_element['statistics'] = {
                        'std_dev': self.convert_to_absolute(float(match.group(1))),
                        'min_value': self.convert_to_absolute(float(match.group(2))),
                        'max_value': self.convert_to_absolute(float(match.group(3))),
                        'form_error': self.convert_to_absolute(float(match.group(4)))
                    }
            
            if '基本座標系' in line:
                self.coordinate_system_data['name'] = line
                for j in range(i+1, min(i+10, len(lines))):
                    datum_line = lines[j].strip()
                    if 'ﾃﾞｰﾀﾑ' in datum_line:
                        if 'datums' not in self.coordinate_system_data:
                            self.coordinate_system_data['datums'] = []
                        self.coordinate_system_data['datums'].append(datum_line)
        
        if current_element:
            self.measurement_data.append(current_element)
    
    def create_detailed_dataframe(self):
        """Create a detailed pandas DataFrame with all measurement data"""
        detailed_data = []
        
        for element in self.measurement_data:
            # Ensure Japanese text is properly encoded
            element_name = ensure_japanese_text(element['name'])
            element_type = ensure_japanese_text(element['type'])
            element_side = ensure_japanese_text(element.get('side', 'N/A'))
            
            base_info = {
                '要素名': element_name,
                'タイプ': element_type,
                '点数': element.get('point_count', 'N/A'),
                '側面': element_side
            }
            
            if 'statistics' in element:
                base_info.update({
                    '標準偏差': element['statistics'].get('std_dev'),
                    '最小値': element['statistics'].get('min_value'),
                    '最大値': element['statistics'].get('max_value'),
                    '形状誤差': element['statistics'].get('form_error')
                })
            
            if 'diameter' in element:
                base_info.update({
                    '直径_実測値': element['diameter']['measured'],
                    '直径_基準値': element['diameter']['reference'],
                    '直径_偏差': self.convert_to_absolute(element['diameter']['measured'] - element['diameter']['reference'])
                })
            
            if element.get('coordinates'):
                for coord_name, coord_data in element['coordinates'].items():
                    row = base_info.copy()
                    within_tolerance = coord_data['lower_tol'] <= coord_data['deviation'] <= coord_data['upper_tol']
                    
                    # Ensure coordinate name and axis are properly encoded
                    coord_name_clean = ensure_japanese_text(coord_name)
                    coord_axis_clean = ensure_japanese_text(coord_data['axis'])
                    
                    row.update({
                        '座標名': coord_name_clean,
                        '軸': coord_axis_clean,
                        '実測値': coord_data['measured'],
                        '基準値': coord_data['reference'],
                        '上限公差': coord_data['upper_tol'],
                        '下限公差': coord_data['lower_tol'],
                        '偏差': coord_data['deviation'],
                        '公差内': 'OK' if within_tolerance else 'NG'
                    })
                    detailed_data.append(row)
            else:
                detailed_data.append(base_info)
        
        return pd.DataFrame(detailed_data)

# Title and description - Preserving your custom title
st.markdown("# Zeiss社測定レポート解析アプリ\nsponsored by 株式会社平田商店")
st.markdown("**Carl Zeiss CALYPSO レポート解析器**")

# Sidebar - Preserving your simplified sidebar
with st.sidebar:
    st.header("使い方")
    st.markdown("1. PDFファイルをアップロード")
    st.markdown("2. ファイル処理開始をクリックしてデータを解析処理")
    st.markdown("3. CSVレポートをダウンロード")
    
    st.header("📊 機能")
    st.markdown("- 詳細解析データ")
    st.markdown("- 絶対値変換済み")
    st.markdown("- 日本語対応エンコーディング")

# File upload
st.header("📁 ファイルアップロード")
uploaded_file = st.file_uploader(
    "PDFファイルを選択してください",
    type="pdf",
    help="Carl Zeiss CALYPSO 測定レポート（PDF形式）をアップロードしてください"
)

if uploaded_file is not None:
    # Show file details
    st.success(f"✅ ファイルアップロード完了: {uploaded_file.name}")
    st.info(f"📄 ファイルサイズ: {uploaded_file.size} バイト")
    
    # Process button
    if st.button("🔄 ファイル処理開始", type="primary"):
        with st.spinner("PDFファイルを処理中..."):
            # Initialize parser
            parser = CMMDataParser()
            
            # Extract text
            file_content = uploaded_file.read()
            text = parser.extract_pdf_text(file_content)
            
            if text:
                # Parse data
                parser.parse_cmm_data(text)
                
                # Store in session state
                st.session_state.parser = parser
                st.session_state.processed = True
                
                st.success("✅ ファイル処理が正常に完了しました！")
            else:
                st.error("❌ PDFからのテキスト抽出に失敗しました")

# Display results if processed
if hasattr(st.session_state, 'processed') and st.session_state.processed:
    parser = st.session_state.parser
    
    # Data table - Only detailed view
    st.header("📋 測定データ（詳細）")
    
    st.subheader("詳細解析データ")
    detailed_df = parser.create_detailed_dataframe()
    
    # Show data info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("データ行数", len(detailed_df))
    with col2:
        st.metric("データ列数", len(detailed_df.columns))
    with col3:
        ok_count = len(detailed_df[detailed_df.get('公差内', 'N/A') == 'OK']) if '公差内' in detailed_df.columns else 0
        st.metric("公差内データ", ok_count)
    
    # Display the dataframe
    st.dataframe(detailed_df, use_container_width=True)
    
    # Generate timestamp for filenames
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Multiple download options for Japanese encoding
    st.subheader("📥 CSVダウンロード")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # UTF-8 with BOM (Excel compatible)
        try:
            csv_utf8_bom = convert_df_to_csv(detailed_df, 'utf-8-sig')
            st.download_button(
                label="📥 Excel推奨 (UTF-8 BOM)",
                data=csv_utf8_bom,
                file_name=f"CMM詳細データ_Excel_{timestamp}.csv",
                mime="text/csv",
                type="primary",
                help="Microsoft Excel で日本語を正しく表示"
            )
        except Exception as e:
            st.error(f"UTF-8 BOM エラー: {e}")
    
    with col2:
        # UTF-8 without BOM
        try:
            csv_utf8 = convert_df_to_csv(detailed_df, 'utf-8')
            st.download_button(
                label="📥 標準 (UTF-8)",
                data=csv_utf8,
                file_name=f"CMM詳細データ_標準_{timestamp}.csv",
                mime="text/csv",
                help="Google Sheets, LibreOffice 向け"
            )
        except Exception as e:
            st.error(f"UTF-8 エラー: {e}")
    
    with col3:
        # Shift-JIS for Japanese systems
        try:
            csv_sjis = convert_df_to_csv(detailed_df, 'shift_jis')
            st.download_button(
                label="📥 日本語システム (Shift-JIS)",
                data=csv_sjis,
                file_name=f"CMM詳細データ_日本語_{timestamp}.csv",
                mime="text/csv",
                help="日本語システム向け"
            )
        except Exception as e:
            st.warning("Shift-JIS エンコーディングは利用できません")
    
    # Encoding help section
    with st.expander("❓ どのファイルをダウンロードすればよいですか？"):
        st.markdown("""
        **推奨ダウンロード:**
        
        - **📊 Microsoft Excel を使用** → Excel推奨 (UTF-8 BOM)
        - **📈 Google Sheets を使用** → 標準 (UTF-8)  
        - **🇯🇵 古い日本語システム** → 日本語システム (Shift-JIS)
        
        **文字化けする場合:**
        1. 異なるエンコーディングのファイルを試してください
        2. Excel の場合：データ > テキストから > エンコーディング選択
        3. メモ帳で開いて日本語が正しく表示されるか確認してください
        """)
    
    # Show data preview
    with st.expander("📄 データプレビュー（最初の10行）"):
        st.dataframe(detailed_df.head(10))