"""
Utility functions for Excel parsing and data extraction.
Handles file parsing, text normalization, and data extraction rules.
"""

import pandas as pd
import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def parse_excel(file_path: str) -> List[Dict[str, str]]:
    """
    Parse Excel file and extract seller information.
    
    Args:
        file_path: Path to the uploaded Excel file
        
    Returns:
        List of dictionaries containing Seller Name and Seller Address
    """
    try:
        # Read Excel file - try different header rows
        # First try with header=2 (common for EXIM reports where headers are in row 2)
        df = None
        seller_name_col = None
        seller_address_col = None
        
        # Try reading with header=2 first (for EXIM Trade reports)
        # Try multiple methods to handle different Excel file formats
        df = None
        last_error = None
        
        try:
            # Method 1: Try with openpyxl engine (for .xlsx files)
            if file_path.endswith('.xlsx'):
                try:
                    # First check if file is valid by trying to open it
                    import zipfile
                    try:
                        with zipfile.ZipFile(file_path, 'r') as z:
                            if '[Content_Types].xml' not in z.namelist():
                                raise ValueError("Invalid Excel file: missing [Content_Types].xml")
                    except zipfile.BadZipFile:
                        raise ValueError("File is not a valid ZIP archive (corrupted .xlsx file)")
                    
                    df = pd.read_excel(file_path, header=2, engine='openpyxl')
                    logger.info(f"Successfully read Excel file with openpyxl engine, header=2")
                except Exception as e1:
                    last_error = str(e1)
                    logger.warning(f"openpyxl engine with header=2 failed: {str(e1)}")
                    # Method 2: Try without specifying engine (pandas will auto-detect)
                    try:
                        df = pd.read_excel(file_path, header=2)
                        logger.info(f"Successfully read Excel file with auto-detect engine, header=2")
                    except Exception as e2:
                        logger.warning(f"Auto-detect engine with header=2 failed: {str(e2)}")
                        # Method 3: Try with header=1
                        try:
                            df = pd.read_excel(file_path, header=1, engine='openpyxl')
                            logger.info(f"Successfully read Excel file with openpyxl engine, header=1")
                        except Exception as e3:
                            logger.warning(f"openpyxl engine with header=1 failed: {str(e3)}")
                            # Method 4: Try with header=0
                            try:
                                df = pd.read_excel(file_path, header=0, engine='openpyxl')
                                logger.info(f"Successfully read Excel file with openpyxl engine, header=0")
                            except Exception as e4:
                                logger.warning(f"openpyxl engine with header=0 failed: {str(e4)}")
                                raise ValueError(f"Could not read Excel file. Last error: {str(e1)}")
            else:
                # For .xls files, try xlrd engine
                try:
                    df = pd.read_excel(file_path, header=2, engine='xlrd')
                except:
                    try:
                        df = pd.read_excel(file_path, header=1, engine='xlrd')
                    except:
                        df = pd.read_excel(file_path, header=2)
            
            # Check if we have proper column names
            if 'SELLER' in df.columns.str.upper().values or 'SELLER ADDRESS' in df.columns.str.upper().values:
                # Found proper headers
                for col in df.columns:
                    col_upper = str(col).upper()
                    if 'SELLER' in col_upper and 'ADDRESS' in col_upper:
                        seller_address_col = col
                    elif 'SELLER' in col_upper and 'ADDRESS' not in col_upper and 'COUNTRY' not in col_upper and 'STATE' not in col_upper and 'CITY' not in col_upper:
                        seller_name_col = col
        except Exception as e:
            logger.warning(f"Error reading with header=2: {str(e)}")
            pass
        
        # If that didn't work, try header=1
        if df is None or seller_name_col is None or seller_address_col is None:
            try:
                if file_path.endswith('.xlsx'):
                    try:
                        df = pd.read_excel(file_path, header=1, engine='openpyxl')
                    except:
                        df = pd.read_excel(file_path, header=1)
                else:
                    df = pd.read_excel(file_path, header=1)
                for col in df.columns:
                    col_upper = str(col).upper()
                    if 'SELLER' in col_upper and 'ADDRESS' in col_upper:
                        seller_address_col = col
                    elif 'SELLER' in col_upper and 'ADDRESS' not in col_upper and 'COUNTRY' not in col_upper and 'STATE' not in col_upper and 'CITY' not in col_upper:
                        seller_name_col = col
            except Exception as e:
                logger.warning(f"Error reading with header=1: {str(e)}")
                pass
        
        # If still not found, try header=0 or use index-based
        if df is None:
            try:
                if file_path.endswith('.xlsx'):
                    try:
                        df = pd.read_excel(file_path, engine='openpyxl')
                    except:
                        df = pd.read_excel(file_path)
                else:
                    df = pd.read_excel(file_path)
            except Exception as e:
                raise ValueError(f"Could not read Excel file: {str(e)}. Please ensure the file is a valid Excel file (.xlsx or .xls format).")
        
        # If columns not found by name, use index-based (Column P = index 15, Column O = index 14)
        if seller_name_col is None:
            # Try to find by name variations
            for col in df.columns:
                col_upper = str(col).upper()
                if 'SELLER' in col_upper and 'ADDRESS' not in col_upper and 'COUNTRY' not in col_upper and 'STATE' not in col_upper and 'CITY' not in col_upper:
                    seller_name_col = col
                    break
            
            # If still not found, use index 15 (Column P)
            if seller_name_col is None and len(df.columns) > 15:
                seller_name_col = df.columns[15]
        
        if seller_address_col is None:
            # Try to find by name variations
            for col in df.columns:
                col_upper = str(col).upper()
                if 'SELLER' in col_upper and 'ADDRESS' in col_upper:
                    seller_address_col = col
                    break
            
            # If still not found, use index 14 (Column O)
            if seller_address_col is None and len(df.columns) > 14:
                seller_address_col = df.columns[14]
        
        if seller_name_col is None or seller_address_col is None:
            raise ValueError("Could not find Seller Name (Column P) or Seller Address (Column O)")
        
        seller_data = []
        
        # Extract rows where Seller Name is present and address is Indian
        for idx, row in df.iterrows():
            seller_name = normalize_text(row.get(seller_name_col))
            seller_address = normalize_text(row.get(seller_address_col))
            
            # Only add rows where Seller Name is present AND address is Indian
            if seller_name and seller_name != '':
                # Check if address is Indian (if address is provided)
                if seller_address:
                    if is_indian_address(seller_address):
                        seller_data.append({
                            'seller_name': seller_name,
                            'seller_address': seller_address,
                            'row_index': idx
                        })
                else:
                    # If no address, include it but it will be filtered during scraping
                    # We'll add "India" to search query to focus on Indian businesses
                    seller_data.append({
                        'seller_name': seller_name,
                        'seller_address': '',
                        'row_index': idx
                    })
        
        return seller_data
    
    except Exception as e:
        raise ValueError(f"Error parsing Excel file: {str(e)}")


def normalize_text(text: any) -> str:
    """
    Normalize text: trim spaces, handle NaNs, normalize case.
    
    Args:
        text: Input text (can be string, NaN, None, etc.)
        
    Returns:
        Normalized string
    """
    if pd.isna(text) or text is None:
        return ''
    
    # Convert to string and strip whitespace
    text = str(text).strip()
    
    # Return empty string if result is empty or 'nan'
    if not text or text.lower() == 'nan':
        return ''
    
    return text


def is_indian_address(address: str) -> bool:
    """
    Check if an address is Indian based on common Indian location indicators.
    
    Args:
        address: Address string to check
        
    Returns:
        True if address appears to be Indian, False otherwise
    """
    if not address:
        return False
    
    address_lower = address.lower()
    
    # Indian state names
    indian_states = [
        'andhra pradesh', 'arunachal pradesh', 'assam', 'bihar', 'chhattisgarh',
        'goa', 'gujarat', 'haryana', 'himachal pradesh', 'jharkhand', 'karnataka',
        'kerala', 'madhya pradesh', 'maharashtra', 'manipur', 'meghalaya', 'mizoram',
        'nagaland', 'odisha', 'punjab', 'rajasthan', 'sikkim', 'tamil nadu', 'telangana',
        'tripura', 'uttar pradesh', 'uttarakhand', 'west bengal',
        'delhi', 'jammu and kashmir', 'ladakh', 'puducherry', 'chandigarh',
        'daman and diu', 'dadra and nagar haveli', 'lakshadweep', 'andaman and nicobar'
    ]
    
    # Indian cities (major ones)
    indian_cities = [
        'mumbai', 'delhi', 'bangalore', 'hyderabad', 'ahmedabad', 'chennai', 'kolkata',
        'pune', 'jaipur', 'surat', 'lucknow', 'kanpur', 'nagpur', 'indore', 'thane',
        'bhopal', 'visakhapatnam', 'patna', 'vadodara', 'ghaziabad', 'ludhiana', 'agra',
        'nashik', 'faridabad', 'meerut', 'rajkot', 'varanasi', 'srinagar', 'amritsar',
        'noida', 'ranchi', 'howrah', 'jabalpur', 'gwalior', 'coimbatore', 'vijayawada',
        'jodhpur', 'madurai', 'raipur', 'kota', 'guwahati', 'chandigarh', 'solapur'
    ]
    
    # Indian postal code pattern (PIN code: 6 digits)
    pin_code_pattern = r'\b\d{6}\b'
    
    # Indian country indicators
    country_indicators = ['india', 'indian', 'bharat', 'hindustan']
    
    # Check for country indicators
    if any(indicator in address_lower for indicator in country_indicators):
        return True
    
    # Check for state names
    if any(state in address_lower for state in indian_states):
        return True
    
    # Check for city names
    if any(city in address_lower for city in indian_cities):
        return True
    
    # Check for PIN code pattern
    if re.search(pin_code_pattern, address):
        return True
    
    # Check for common Indian address patterns
    indian_patterns = [
        r'\b\d{6}\b',  # PIN code
        r'\b(maharashtra|gujarat|karnataka|tamil nadu|west bengal|rajasthan|punjab)',
        r'\b(mumbai|delhi|bangalore|hyderabad|chennai|kolkata|pune)',
    ]
    
    for pattern in indian_patterns:
        if re.search(pattern, address_lower):
            return True
    
    return False


def build_search_query(seller_name: str, seller_address: str) -> str:
    """
    Build a search query from seller name and address.
    Always includes "India" to focus on Indian businesses.
    
    Args:
        seller_name: Seller name
        seller_address: Seller address
        
    Returns:
        Combined search query string with India focus
    """
    query_parts = [seller_name]
    
    if seller_address:
        query_parts.append(seller_address)
    
    # Always add "India" to focus search on Indian businesses
    query_parts.append('India')
    
    return ' '.join(query_parts)


def extract_email(text: str) -> List[str]:
    """
    Extract email addresses from text using regex.
    
    Args:
        text: Text to search for emails
        
    Returns:
        List of found email addresses
    """
    if not text:
        return []
    
    # Email regex pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text, re.IGNORECASE)
    
    # Remove duplicates and return
    return list(set(emails))


def extract_phone(text: str) -> List[str]:
    """
    Extract Indian phone numbers from text using regex.
    Only matches Indian phone numbers (+91 or 10-digit numbers).
    
    Args:
        text: Text to search for phone numbers
        
    Returns:
        List of found Indian phone numbers
    """
    if not text:
        return []
    
    # Indian phone number patterns
    # Format: +91-XXXXX-XXXXX, 91-XXXXX-XXXXX, +91 XXXXX XXXXX, or 10-digit numbers
    phone_patterns = [
        r'\+91[-.\s]?[6-9]\d{9}',  # +91 followed by 10 digits starting with 6-9
        r'91[-.\s]?[6-9]\d{9}',    # 91 followed by 10 digits starting with 6-9
        r'[6-9]\d{9}',              # 10-digit number starting with 6-9 (mobile)
        r'\+91[-.\s]?\d{2,4}[-.\s]?\d{6,8}',  # +91 with area code (landline)
        r'0?[1-9]\d{2,4}[-.\s]?\d{6,8}',      # Landline with optional leading 0
    ]
    
    phones = []
    for pattern in phone_patterns:
        matches = re.findall(pattern, text)
        phones.extend(matches)
    
    # Clean and validate Indian phone numbers
    cleaned_phones = []
    for phone in phones:
        # Remove common separators for validation
        cleaned = re.sub(r'[-.\s()]', '', phone)
        
        # Validate Indian phone number
        # Should be: 10 digits (mobile) or 91 + 10 digits, or landline format
        if cleaned.startswith('91'):
            # Remove country code for validation
            digits = cleaned[2:]
            if len(digits) == 10 and digits[0] in '6789':
                cleaned_phones.append(phone.strip())
        elif cleaned.startswith('+91'):
            digits = cleaned[3:]
            if len(digits) == 10 and digits[0] in '6789':
                cleaned_phones.append(phone.strip())
        elif len(cleaned) == 10 and cleaned[0] in '6789':
            # 10-digit mobile number
            cleaned_phones.append(phone.strip())
        elif len(cleaned) >= 10 and len(cleaned) <= 13:
            # Landline numbers (with area code)
            cleaned_phones.append(phone.strip())
    
    # Return the first valid Indian phone number (prefer +91 format if available)
    if cleaned_phones:
        # Prefer +91 format, then 91 format, then plain 10-digit
        for phone in cleaned_phones:
            if phone.startswith('+91'):
                return [phone]
        for phone in cleaned_phones:
            if phone.startswith('91'):
                return [phone]
        # Return first valid 10-digit number
        return [cleaned_phones[0]]
    
    return []


def extract_contact_name(text: str) -> Optional[str]:
    """
    Extract contact name from text (heuristic approach).
    
    Args:
        text: Text to search for contact names
        
    Returns:
        Contact name if found, None otherwise
    """
    if not text:
        return None
    
    # Common patterns for contact names
    # Look for "Contact:", "Name:", "Manager:", etc.
    patterns = [
        r'(?:Contact|Name|Manager|Director)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # Simple two-word capitalized name
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return None


def generate_output_excel(seller_data: List[Dict], output_path: str):
    """
    Generate output Excel file with enriched contact details.
    
    Args:
        seller_data: List of dictionaries with seller and contact information
        output_path: Path where output Excel file should be saved
    """
    # Prepare data for DataFrame
    output_data = []
    
    for item in seller_data:
        output_data.append({
            'Seller Name': item.get('seller_name', ''),
            'Seller Address': item.get('seller_address', ''),
            'Contact Name': item.get('contact_name', ''),
            'Contact Address': item.get('contact_address', ''),
            'Email': item.get('email', ''),
            'Phone Number': item.get('phone', ''),
            'WhatsApp Number': item.get('whatsapp', ''),  # Add WhatsApp column
            'Source URL': item.get('source_url', '')
        })
    
    # Create DataFrame and save to Excel
    df = pd.DataFrame(output_data)
    df.to_excel(output_path, index=False, engine='openpyxl')

