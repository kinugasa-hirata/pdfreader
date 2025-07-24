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
        """Extract text from PDF file"""
        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
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
            base_info = {
                '要素名': element['name'],
                'タイプ': element['type'],
                '点数': element.get('point_count', 'N/A'),
                '側面': element.get('side', 'N/A')
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
                    row.update({
                        '座標名': coord_name,
                        '軸': coord_data['axis'],
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

def convert_df_to_csv(df):
    """Convert DataFrame to CSV string"""
    return df.to_csv(index=False, encoding='utf-8-sig')

# Title and description - MOVED OUTSIDE OF MAIN FUNCTION
st.title("📐 CMM データパーサー")
st.markdown("**Carl Zeiss CALYPSO レポート解析器**")
st.markdown("CMM測定PDFレポートをアップロードして、データを解析・分析してください。")

# Sidebar - MOVED OUTSIDE OF MAIN FUNCTION
with st.sidebar:
    st.header("📋 ナビゲーション")
    st.markdown("1. PDFファイルをアップロード")
    st.markdown("2. 解析データを確認")
    st.markdown("3. CSVレポートをダウンロード")
    
    st.header("📊 エクスポート機能")
    st.markdown("- 詳細解析データ")
    st.markdown("- 座標系情報")
    st.markdown("- 絶対値変換済み")

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
    
    # Overview
    st.header("📊 解析概要")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("総要素数", len(parser.measurement_data))
    
    with col2:
        type_counts = {}
        for element in parser.measurement_data:
            element_type = element['type']
            type_counts[element_type] = type_counts.get(element_type, 0) + 1
        st.metric("要素タイプ数", len(type_counts))
    
    with col3:
        total_coordinates = sum(len(element.get('coordinates', {})) for element in parser.measurement_data)
        st.metric("座標数", total_coordinates)
    
    with col4:
        if parser.coordinate_system_data:
            datum_count = len(parser.coordinate_system_data.get('datums', []))
            st.metric("データム数", datum_count)
    
    # Element type breakdown
    if type_counts:
        st.subheader("🔍 要素タイプ別内訳")
        # Translate type names to Japanese
        japanese_types = {
            'circle': '円',
            'plane': '平面', 
            'line': '直線'
        }
        
        translated_counts = {}
        for eng_type, count in type_counts.items():
            jp_type = japanese_types.get(eng_type, eng_type)
            translated_counts[jp_type] = count
            
        type_df = pd.DataFrame(list(translated_counts.items()), columns=['タイプ', '数量'])
        st.bar_chart(type_df.set_index('タイプ'))
    
    # Coordinate system info
    if parser.coordinate_system_data:
        st.subheader("🎯 座標系")
        st.info(f"**名前:** {parser.coordinate_system_data.get('name', 'N/A')}")
        if 'datums' in parser.coordinate_system_data:
            with st.expander("データム一覧"):
                for i, datum in enumerate(parser.coordinate_system_data['datums']):
                    st.write(f"**データム {i+1}:** {datum}")
    
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
    
    # Download button
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    detailed_filename = f"CMM詳細データ_{timestamp}.csv"
    
    st.download_button(
        label="📥 詳細データCSVダウンロード",
        data=convert_df_to_csv(detailed_df),
        file_name=detailed_filename,
        mime="text/csv",
        type="primary",
        help="絶対値変換済みの詳細測定データをCSVファイルとしてダウンロードします"
    )
    
    # Show data preview
    with st.expander("📄 データプレビュー（最初の10行）"):
        st.dataframe(detailed_df.head(10))
    
    # New file processing
    st.header("🔄 新しいファイルの処理")
    
    if st.button("新しいファイルを処理する"):
        # Clear session state
        if 'processed' in st.session_state:
            del st.session_state.processed
        if 'parser' in st.session_state:
            del st.session_state.parser
        st.rerun()

# Footer
st.markdown("---")
st.markdown("**CMM データパーサー v1.0** | Streamlit で構築 🚀")
st.markdown("💡 **機能:** 全数値データは絶対値に変換されています（負の値 → 正の値）")