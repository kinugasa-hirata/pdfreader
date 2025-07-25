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
    page_title="CMM Data Parser",
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
        """Extract text from PDF file - EXACTLY like Google Colab"""
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
    
    def parse_measurement_line(self, line):
        """Parse a single measurement line to extract values - EXACTLY like Google Colab"""
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
        """Parse the entire CMM measurement text - EXACTLY like Google Colab"""
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
                    
                    # KEEP ORIGINAL JAPANESE - NO TRANSLATION
                    current_element = {
                        'name': parsed_line['match'].group(1),  # Original Japanese preserved
                        'type': parsed_line['type'],
                        'point_count': int(parsed_line['match'].group(2)) if len(parsed_line['match'].groups()) >= 2 else None,
                        'side': parsed_line['match'].group(3) if len(parsed_line['match'].groups()) >= 3 else None,
                        'coordinates': {},
                        'statistics': {},
                        'tolerances': {}
                    }
                
                elif parsed_line['type'] == 'coordinate_value' and current_element:
                    match = parsed_line['match']
                    coord_name = match.group(1)  # Keep original Japanese
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
                self.coordinate_system_data['name'] = line  # Keep original Japanese
                for j in range(i+1, min(i+10, len(lines))):
                    datum_line = lines[j].strip()
                    if 'ﾃﾞｰﾀﾑ' in datum_line:
                        if 'datums' not in self.coordinate_system_data:
                            self.coordinate_system_data['datums'] = []
                        self.coordinate_system_data['datums'].append(datum_line)  # Keep original Japanese
        
        if current_element:
            self.measurement_data.append(current_element)
    
    def create_detailed_dataframe(self):
        """Create a detailed pandas DataFrame - EXACTLY like Google Colab"""
        detailed_data = []
        
        for element in self.measurement_data:
            base_info = {
                'Element_Name': element['name'],  # Keep original Japanese
                'Type': element['type'],
                'Point_Count': element.get('point_count', 'N/A'),
                'Side': element.get('side', 'N/A')
            }
            
            # Add statistics if present
            if 'statistics' in element:
                base_info.update({
                    'Std_Dev': element['statistics'].get('std_dev'),
                    'Min_Value': element['statistics'].get('min_value'),
                    'Max_Value': element['statistics'].get('max_value'),
                    'Form_Error': element['statistics'].get('form_error')
                })
            
            # Add diameter if present
            if 'diameter' in element:
                base_info.update({
                    'Diameter_Measured': element['diameter']['measured'],
                    'Diameter_Reference': element['diameter']['reference'],
                    'Diameter_Deviation': self.convert_to_absolute(element['diameter']['measured'] - element['diameter']['reference'])
                })
            
            # Create separate rows for each coordinate
            if element.get('coordinates'):
                for coord_name, coord_data in element['coordinates'].items():
                    row = base_info.copy()
                    within_tolerance = coord_data['lower_tol'] <= coord_data['deviation'] <= coord_data['upper_tol']
                    row.update({
                        'Coordinate_Name': coord_name,  # Keep original Japanese
                        'Axis': coord_data['axis'],
                        'Measured_Value': coord_data['measured'],
                        'Reference_Value': coord_data['reference'],
                        'Upper_Tolerance': coord_data['upper_tol'],
                        'Lower_Tolerance': coord_data['lower_tol'],
                        'Deviation': coord_data['deviation'],
                        'Within_Tolerance': coord_data['lower_tol'] <= coord_data['deviation'] <= coord_data['upper_tol']
                    })
                    detailed_data.append(row)
            else:
                # If no coordinates, add the base info as a single row
                detailed_data.append(base_info)
        
        return pd.DataFrame(detailed_data)

def convert_df_to_csv(df):
    """Convert DataFrame to CSV string - EXACTLY like Google Colab"""
    return df.to_csv(index=False, encoding='utf-8-sig')

# Title and description - Your custom title
st.markdown("# Zeiss社pdf出力データ解析アプリ\nmade by Hirata Trading Co., Ltd.")

# Sidebar
with st.sidebar:
    st.header("使い方")
    st.markdown("1. PDFファイルをアプロード")
    st.markdown("2. Process Fileをクリックして解析開始")
    st.markdown("3. CSVファイルをダウンロード")
    
# File upload
st.header("PDFファイルをアップロード")
uploaded_file = st.file_uploader(type="pdf", label="PDFファイルをアップロード")

if uploaded_file is not None:
    # Show file details
    st.success(f"✅ ファイルのアップロードが完了しました: {uploaded_file.name}")
    
    # Process button
    if st.button("🔄 Process File", type="primary"):
        with st.spinner("ファイルを処理しています..."):
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
                
                st.success("✅ ファイル処理が完了しました!")
            else:
                st.error("❌ Failed to extract text from PDF")

# Display results if processed
if hasattr(st.session_state, 'processed') and st.session_state.processed:
    parser = st.session_state.parser
    
    st.subheader("解析データ")
    detailed_df = parser.create_detailed_dataframe()
    
    # Display the dataframe
    st.dataframe(detailed_df, use_container_width=True)
    
    # Download button - EXACTLY like Google Colab approach
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    detailed_filename = f"CMM_Detailed_Data_{timestamp}.csv"
    
    st.download_button(
        label="CSVデータをダウンロードします",
        data=convert_df_to_csv(detailed_df),
        file_name=detailed_filename,
        mime="text/csv",
        type="primary",
    )
    
    # Show data preview
    with st.expander("📄 Data Preview (First 10 rows)"):
        st.dataframe(detailed_df.head(10))


# import streamlit as st
# import pandas as pd
# import re
# import PyPDF2
# import io
# from typing import Dict, List, Any
# import numpy as np
# import datetime
# import base64

# # Set page config - MUST be first Streamlit command
# st.set_page_config(
#     page_title="CMM Data Parser",
#     page_icon="📐",
#     layout="wide",
#     initial_sidebar_state="expanded"
# )

# class CMMDataParser:
#     def __init__(self):
#         self.measurement_data = []
#         self.coordinate_system_data = {}
#         self.reference_elements = {}
        
#         # Translation dictionary for Japanese to English
#         self.japanese_to_english = {
#             # Element types
#             '円': 'Circle',
#             '平面': 'Plane', 
#             '線': 'Line',
#             '基準円': 'Reference_Circle',
#             '直線': 'Line',
            
#             # Sides and positions
#             '内側': 'Inside',
#             '外側': 'Outside',
            
#             # Common measurement terms
#             'ロハ': 'RoHa',
#             'イロ': 'IrO', 
#             'ハニ': 'HaNi',
#             'イニ': 'IniNi',
#             'ニ': 'Ni',
#             'ロ': 'Ro',
#             'ハ': 'Ha',
#             'イ': 'I',
            
#             # Coordinate system terms
#             '基本座標系': 'Basic_Coordinate_System',
#             'ﾃﾞｰﾀﾑ': 'Datum',
#             '座標系': 'Coordinate_System',
            
#             # Common prefixes
#             '基準': 'Reference',
#             '測定': 'Measurement',
#             '点数': 'Point_Count',
            
#             # Numbers in Japanese context
#             '１': '1', '２': '2', '３': '3', '４': '4', '５': '5',
#             '６': '6', '７': '7', '８': '8', '９': '9', '０': '0',
            
#             # Additional common terms
#             '値': 'Value',
#             '軸': 'Axis',
#             '形状': 'Form',
#             '公差': 'Tolerance',
#             '偏差': 'Deviation',
#         }
    
#     def translate_japanese_to_english(self, text):
#         """Translate Japanese text to English alphabets"""
#         if not isinstance(text, str):
#             return text
            
#         # Handle None or empty strings
#         if not text or text == 'N/A':
#             return text
            
#         translated = text
        
#         # Apply translations
#         for japanese, english in self.japanese_to_english.items():
#             translated = translated.replace(japanese, english)
        
#         # Convert specific patterns
#         patterns = [
#             (r'Circle(\d+)', r'Circle_\1'),
#             (r'Plane(\d+)', r'Plane_\1'),
#             (r'Reference_Circle(\d+)', r'Ref_Circle_\1'),
#             (r'([A-Za-z]+)線', r'\1_Line'),
#             (r'([XYZ])-値_', r'\1_Value_'),
#         ]
        
#         for pattern, replacement in patterns:
#             translated = re.sub(pattern, replacement, translated)
        
#         # Remove any remaining Japanese characters and replace with placeholders
#         # This catches any characters we didn't explicitly translate
#         result = ""
#         for char in translated:
#             if ord(char) > 127:  # Non-ASCII character
#                 result += "X"  # Replace with X as placeholder
#             else:
#                 result += char
                
#         return result
        
#     def convert_to_absolute(self, value):
#         """Convert numerical value to absolute value"""
#         try:
#             if isinstance(value, (int, float)):
#                 return abs(value)
#             elif isinstance(value, str):
#                 try:
#                     num_value = float(value)
#                     return abs(num_value)
#                 except ValueError:
#                     return value
#             else:
#                 return value
#         except:
#             return value
        
#     def extract_pdf_text(self, file_content):
#         """Extract text from PDF file"""
#         try:
#             pdf_file = io.BytesIO(file_content)
#             pdf_reader = PyPDF2.PdfReader(pdf_file)
            
#             text = ""
#             for page in pdf_reader.pages:
#                 text += page.extract_text() + "\n"
            
#             return text
#         except Exception as e:
#             st.error(f"Error extracting PDF text: {e}")
#             return None
    
#     def parse_measurement_line(self, line):
#         """Parse a single measurement line to extract values"""
#         patterns = {
#             'circle': r'(円\d+|基準円\d+)\s+円\(最小二乗法\)\s+点数\s+\((\d+)\)\s+(内側|外側)?',
#             'plane': r'(平面\d+|.*平面)\s+平面\(最小二乗法\)\s+点数\s+\((\d+)\)',
#             'line': r'(.*線)\s+直線\(最小二乗法\)\s+点数\s+\((\d+)\)',
#             'coordinate_value': r'([XYZ]-値_.*?|[XYZ])\s+([XYZ])\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)',
#             'diameter': r'D\s+([\d.]+)\s+([\d.]+)',
#             'statistics': r'S=\s+([\d.]+)\s+Min=\([^)]+\)\s+([-\d.]+)\s+Max=\([^)]+\)\s+([-\d.]+)\s+形状=\s+([\d.]+)'
#         }
        
#         result = {}
        
#         for pattern_name, pattern in patterns.items():
#             match = re.search(pattern, line)
#             if match:
#                 result['type'] = pattern_name
#                 result['match'] = match
#                 break
                
#         return result if result else None
    
#     def parse_cmm_data(self, text):
#         """Parse the entire CMM measurement text"""
#         lines = text.split('\n')
#         current_element = None
        
#         for i, line in enumerate(lines):
#             line = line.strip()
#             if not line:
#                 continue
            
#             parsed_line = self.parse_measurement_line(line)
            
#             if parsed_line:
#                 if parsed_line['type'] in ['circle', 'plane', 'line']:
#                     if current_element:
#                         self.measurement_data.append(current_element)
                    
#                     # Translate Japanese element names to English
#                     element_name = self.translate_japanese_to_english(parsed_line['match'].group(1))
#                     element_side = None
#                     if len(parsed_line['match'].groups()) >= 3 and parsed_line['match'].group(3):
#                         element_side = self.translate_japanese_to_english(parsed_line['match'].group(3))
                    
#                     current_element = {
#                         'name': element_name,
#                         'type': parsed_line['type'],
#                         'point_count': int(parsed_line['match'].group(2)) if len(parsed_line['match'].groups()) >= 2 else None,
#                         'side': element_side,
#                         'coordinates': {},
#                         'statistics': {},
#                         'tolerances': {}
#                     }
                
#                 elif parsed_line['type'] == 'coordinate_value' and current_element:
#                     match = parsed_line['match']
#                     # Translate coordinate names to English
#                     coord_name = self.translate_japanese_to_english(match.group(1))
#                     coord_axis = match.group(2)  # X, Y, Z are already English
#                     measured_value = self.convert_to_absolute(float(match.group(3)))
#                     reference_value = self.convert_to_absolute(float(match.group(4)))
#                     upper_tolerance = self.convert_to_absolute(float(match.group(5)))
#                     lower_tolerance = self.convert_to_absolute(float(match.group(6)))
#                     deviation = self.convert_to_absolute(float(match.group(7)))
                    
#                     current_element['coordinates'][coord_name] = {
#                         'axis': coord_axis,
#                         'measured': measured_value,
#                         'reference': reference_value,
#                         'upper_tol': upper_tolerance,
#                         'lower_tol': lower_tolerance,
#                         'deviation': deviation
#                     }
                
#                 elif parsed_line['type'] == 'diameter' and current_element:
#                     match = parsed_line['match']
#                     current_element['diameter'] = {
#                         'measured': self.convert_to_absolute(float(match.group(1))),
#                         'reference': self.convert_to_absolute(float(match.group(2)))
#                     }
                
#                 elif parsed_line['type'] == 'statistics' and current_element:
#                     match = parsed_line['match']
#                     current_element['statistics'] = {
#                         'std_dev': self.convert_to_absolute(float(match.group(1))),
#                         'min_value': self.convert_to_absolute(float(match.group(2))),
#                         'max_value': self.convert_to_absolute(float(match.group(3))),
#                         'form_error': self.convert_to_absolute(float(match.group(4)))
#                     }
            
#             if '基本座標系' in line:
#                 # Translate coordinate system info to English
#                 translated_line = self.translate_japanese_to_english(line)
#                 self.coordinate_system_data['name'] = translated_line
#                 for j in range(i+1, min(i+10, len(lines))):
#                     datum_line = lines[j].strip()
#                     if 'ﾃﾞｰﾀﾑ' in datum_line:
#                         if 'datums' not in self.coordinate_system_data:
#                             self.coordinate_system_data['datums'] = []
#                         translated_datum = self.translate_japanese_to_english(datum_line)
#                         self.coordinate_system_data['datums'].append(translated_datum)
        
#         if current_element:
#             self.measurement_data.append(current_element)
    
#     def create_detailed_dataframe(self):
#         """Create a detailed pandas DataFrame with all measurement data"""
#         detailed_data = []
        
#         for element in self.measurement_data:
#             # Ensure all text is translated to English
#             element_name = self.translate_japanese_to_english(element['name'])
#             element_type = element['type']  # Already English from parsing
#             element_side = self.translate_japanese_to_english(element.get('side', 'N/A')) if element.get('side') else 'N/A'
            
#             base_info = {
#                 'Element_Name': element_name,
#                 'Type': element_type,
#                 'Point_Count': element.get('point_count', 'N/A'),
#                 'Side': element_side
#             }
            
#             if 'statistics' in element:
#                 base_info.update({
#                     'Std_Dev': element['statistics'].get('std_dev'),
#                     'Min_Value': element['statistics'].get('min_value'),
#                     'Max_Value': element['statistics'].get('max_value'),
#                     'Form_Error': element['statistics'].get('form_error')
#                 })
            
#             if 'diameter' in element:
#                 base_info.update({
#                     'Diameter_Measured': element['diameter']['measured'],
#                     'Diameter_Reference': element['diameter']['reference'],
#                     'Diameter_Deviation': self.convert_to_absolute(element['diameter']['measured'] - element['diameter']['reference'])
#                 })
            
#             if element.get('coordinates'):
#                 for coord_name, coord_data in element['coordinates'].items():
#                     row = base_info.copy()
#                     within_tolerance = coord_data['lower_tol'] <= coord_data['deviation'] <= coord_data['upper_tol']
                    
#                     # Translate coordinate names to English
#                     coord_name_english = self.translate_japanese_to_english(coord_name)
                    
#                     row.update({
#                         'Coordinate_Name': coord_name_english,
#                         'Axis': coord_data['axis'],  # X, Y, Z already English
#                         'Measured_Value': coord_data['measured'],
#                         'Reference_Value': coord_data['reference'],
#                         'Upper_Tolerance': coord_data['upper_tol'],
#                         'Lower_Tolerance': coord_data['lower_tol'],
#                         'Deviation': coord_data['deviation'],
#                         'Within_Tolerance': 'OK' if within_tolerance else 'NG'
#                     })
#                     detailed_data.append(row)
#             else:
#                 detailed_data.append(base_info)
        
#         return pd.DataFrame(detailed_data)

# def convert_df_to_csv(df):
#     """Convert DataFrame to CSV string"""
#     return df.to_csv(index=False, encoding='utf-8-sig')

# # Title and description - Your custom title
# st.markdown("# Zeiss社pdf出力データ解析アプリ\nmade by Hirata Trading Co., Ltd.")

# # Sidebar
# with st.sidebar:
#     st.header("使い方")
#     st.markdown("1. PDFファイルをアプロード")
#     st.markdown("2. Process Fileをクリックして解析開始")
#     st.markdown("3. CSVファイルをダウンロード")
    
# # File upload
# st.header("PDFファイルをアップロード")
# uploaded_file = st.file_uploader(type="pdf", label="PDFファイルをアップロード",)

# if uploaded_file is not None:
#     # Show file details
#     st.success(f"✅ ファイルのアップロードが完了しました: {uploaded_file.name}")
    
#     # Process button
#     if st.button("🔄 Process File", type="primary"):
#         with st.spinner("ファイルを処理しています..."):
#             # Initialize parser
#             parser = CMMDataParser()
            
#             # Extract text
#             file_content = uploaded_file.read()
#             text = parser.extract_pdf_text(file_content)
            
#             if text:
#                 # Parse data
#                 parser.parse_cmm_data(text)
                
#                 # Store in session state
#                 st.session_state.parser = parser
#                 st.session_state.processed = True
                
#                 st.success("✅ ファイル処理が完了しました!")
#             else:
#                 st.error("❌ Failed to extract text from PDF")

# # Display results if processed
# if hasattr(st.session_state, 'processed') and st.session_state.processed:
#     parser = st.session_state.parser
    
#     st.subheader("解析データ")
#     detailed_df = parser.create_detailed_dataframe()
    
#     # # Show data info
#     # col1, col2, col3 = st.columns(3)
#     # with col1:
#     #     st.metric("Data Rows", len(detailed_df))
#     # with col2:
#     #     st.metric("Data Columns", len(detailed_df.columns))
#     # with col3:
#     #     ok_count = len(detailed_df[detailed_df.get('Within_Tolerance', 'N/A') == 'OK']) if 'Within_Tolerance' in detailed_df.columns else 0
#     #     st.metric("Within Tolerance", ok_count)
    
#     # Display the dataframe
#     st.dataframe(detailed_df, use_container_width=True)
    
#     # Download button
#     timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
#     detailed_filename = f"CMM_Detailed_Data_{timestamp}.csv"
    
#     st.download_button(
#         label="CSVデータをダウンロードします",
#         data=convert_df_to_csv(detailed_df),
#         file_name=detailed_filename,
#         mime="text/csv",
#         type="primary",
#     )
    
#     # Show data preview
#     with st.expander("📄 Data Preview (First 10 rows)"):
#         st.dataframe(detailed_df.head(10))