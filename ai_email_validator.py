"""
AI Email Validator - Uses OpenAI to verify if emails are real/valid.

Strategy:
1. Generate email patterns
2. Use ChatGPT to search and verify if email appears online
3. Check if email pattern is commonly used by the company
4. Return confidence score
"""

import os
import logging
import re
import json
from typing import Dict, List
from openai import OpenAI

logger = logging.getLogger(__name__)


class AIEmailValidator:
    """Validate emails using AI-powered web search and reasoning."""
    
    def __init__(self, openai_api_key: str = None, serpapi_key: str = None):
        """Initialize AI validator."""
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.serpapi_key = serpapi_key or os.getenv('SERPAPI_API_KEY')
        
        if self.openai_api_key:
            self.client = OpenAI(api_key=self.openai_api_key)
            logger.info("✅ AI Email Validator initialized")
        else:
            self.client = None
            logger.warning("⚠️  OpenAI API key not found")
    
    def validate_email(self, email: str, contact_name: str, company_name: str, 
                      company_website: str = None) -> Dict[str, any]:
        """
        Validate if an email is real using AI.
        
        Args:
            email: Email to validate (e.g., "rajesh.kumar@company.com")
            contact_name: Person's name (e.g., "Rajesh Kumar")
            company_name: Company name (e.g., "Star Exports")
            company_website: Company website (optional)
        
        Returns:
            Dict with:
            - is_valid: bool (True if AI confirms email exists)
            - confidence: int (0-100)
            - found_online: bool (True if email found in search results)
            - reasoning: str (AI's explanation)
            - alternative_email: str (if AI found a different email)
        """
        if not self.client:
            return {
                'is_valid': False,
                'confidence': 0,
                'found_online': False,
                'reasoning': 'OpenAI API not available',
                'alternative_email': ''
            }
        
        try:
            # Build verification prompt
            prompt = self._build_validation_prompt(email, contact_name, company_name, company_website)
            
            # Call ChatGPT
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an email verification expert. Your job is to determine if an email address is real and valid by:
1. Analyzing if the email pattern matches the company's typical format
2. Checking if the email appears in online sources
3. Verifying the person's name matches the email
4. Rating confidence (0-100%)

IMPORTANT: 
- If you find the EXACT email mentioned online, confidence = 90-100%
- If pattern seems correct but not found, confidence = 60-80%
- If pattern seems wrong, confidence = 0-50%
- Always provide reasoning"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content.strip()
            logger.debug(f"AI validation response: {result_text[:200]}")
            
            # Parse AI response
            return self._parse_ai_response(result_text, email)
            
        except Exception as e:
            logger.error(f"Error validating email with AI: {str(e)}")
            return {
                'is_valid': False,
                'confidence': 0,
                'found_online': False,
                'reasoning': f'Error: {str(e)[:100]}',
                'alternative_email': ''
            }
    
    def validate_multiple_patterns(self, email_patterns: List[Dict], contact_name: str, 
                                   company_name: str, company_website: str = None) -> Dict[str, any]:
        """
        Validate multiple email patterns and return the best one.
        
        Args:
            email_patterns: List of dicts with 'email', 'pattern', 'confidence'
            contact_name: Person's name
            company_name: Company name
            company_website: Company website (optional)
        
        Returns:
            Dict with best validated email
        """
        if not self.client or not email_patterns:
            return {
                'best_email': '',
                'confidence': 0,
                'found_online': False,
                'reasoning': 'No patterns to validate'
            }
        
        try:
            # Build prompt with all patterns
            patterns_text = "\n".join([f"  - {p['email']} (Pattern: {p['pattern']})" 
                                      for p in email_patterns[:5]])  # Top 5 only
            
            prompt = f"""I need to find the REAL email address for:
- Person: {contact_name}
- Company: {company_name}
- Website: {company_website or 'Unknown'}

Possible email patterns:
{patterns_text}

Please:
1. Search online for which email is actually used
2. Check if any of these emails appear in search results
3. Determine which pattern is most likely correct
4. Return JSON: {{"best_email": "xxx@xxx.com", "confidence": 85, "found_online": true, "reasoning": "Found this email on company website"}}

If no email found online, suggest the most likely pattern based on typical Indian business email formats."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an email verification expert. Analyze patterns and return the most likely valid email in JSON format."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content.strip()
            logger.debug(f"AI pattern validation: {result_text[:200]}")
            
            # Parse response
            result = self._parse_ai_response(result_text)
            
            # If AI found an email, return it
            if result.get('best_email') or result.get('is_valid'):
                return {
                    'best_email': result.get('best_email') or result.get('alternative_email', ''),
                    'confidence': result.get('confidence', 50),
                    'found_online': result.get('found_online', False),
                    'reasoning': result.get('reasoning', 'AI-verified pattern')
                }
            
            # Fallback to first pattern
            return {
                'best_email': email_patterns[0]['email'],
                'confidence': email_patterns[0]['confidence'],
                'found_online': False,
                'reasoning': 'Using most common pattern (not verified)'
            }
            
        except Exception as e:
            logger.error(f"Error validating patterns with AI: {str(e)}")
            return {
                'best_email': email_patterns[0]['email'] if email_patterns else '',
                'confidence': 50,
                'found_online': False,
                'reasoning': f'Error: {str(e)[:100]}'
            }
    
    def _build_validation_prompt(self, email: str, contact_name: str, 
                                 company_name: str, company_website: str = None) -> str:
        """Build prompt for single email validation."""
        prompt = f"""Verify if this email address is real and valid:

Email: {email}
Person: {contact_name}
Company: {company_name}
Website: {company_website or 'Unknown'}

Please:
1. Check if this email appears anywhere online (search results, company website, directories)
2. Verify if the email pattern matches the person's name
3. Check if this pattern is typical for Indian businesses
4. Rate confidence (0-100%)

Return JSON format:
{{
  "is_valid": true/false,
  "confidence": 85,
  "found_online": true/false,
  "reasoning": "Found on company website contact page",
  "alternative_email": "different@email.com" (if you find a better one)
}}

If you can't find this exact email, suggest the most likely email for this person."""
        
        return prompt
    
    def _parse_ai_response(self, response_text: str, default_email: str = '') -> Dict:
        """Parse AI response and extract validation result."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                # Normalize keys
                return {
                    'is_valid': result.get('is_valid', False),
                    'confidence': int(result.get('confidence', 0)),
                    'found_online': result.get('found_online', False),
                    'reasoning': result.get('reasoning', ''),
                    'alternative_email': result.get('alternative_email', ''),
                    'best_email': result.get('best_email', default_email)
                }
            
            # If no JSON, parse text heuristically
            is_valid = any(word in response_text.lower() for word in ['valid', 'correct', 'real', 'found'])
            confidence = 50  # Default
            
            # Try to extract confidence percentage
            conf_match = re.search(r'(\d{1,3})%', response_text)
            if conf_match:
                confidence = int(conf_match.group(1))
            
            found_online = 'found' in response_text.lower() and 'not found' not in response_text.lower()
            
            # Extract alternative email if mentioned
            alt_email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', response_text)
            alternative_email = alt_email_match.group(1) if alt_email_match else ''
            
            return {
                'is_valid': is_valid,
                'confidence': confidence,
                'found_online': found_online,
                'reasoning': response_text[:200],
                'alternative_email': alternative_email,
                'best_email': alternative_email or default_email
            }
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return {
                'is_valid': False,
                'confidence': 0,
                'found_online': False,
                'reasoning': 'Could not parse AI response',
                'alternative_email': '',
                'best_email': default_email
            }


if __name__ == '__main__':
    # Test the AI Email Validator
    logging.basicConfig(level=logging.INFO)
    
    validator = AIEmailValidator()
    
    print("="*70)
    print("AI EMAIL VALIDATOR - TEST")
    print("="*70)
    
    # Test Case 1: Known email
    print("\n🔍 Test 1: Validating known pattern")
    result = validator.validate_email(
        email="manish.khimasia@starexports.in",
        contact_name="Manish Khimasia",
        company_name="Star Exports",
        company_website="https://www.starexports.com"
    )
    
    print(f"   Email: manish.khimasia@starexports.in")
    print(f"   ✅ Valid: {result['is_valid']}")
    print(f"   📊 Confidence: {result['confidence']}%")
    print(f"   🌐 Found Online: {result['found_online']}")
    print(f"   💬 Reasoning: {result['reasoning'][:100]}")
    if result['alternative_email']:
        print(f"   🔄 Alternative: {result['alternative_email']}")
    
    # Test Case 2: Multiple patterns
    print("\n🔍 Test 2: Choosing best from multiple patterns")
    patterns = [
        {'email': 'neha.kedia@hitaashi.com', 'pattern': 'firstname.lastname', 'confidence': 85},
        {'email': 'nehakedia@hitaashi.com', 'pattern': 'firstnamelastname', 'confidence': 80},
        {'email': 'nkedia@hitaashi.com', 'pattern': 'flastname', 'confidence': 75},
    ]
    
    result = validator.validate_multiple_patterns(
        email_patterns=patterns,
        contact_name="Neha Kedia",
        company_name="Hitaashi Solutions"
    )
    
    print(f"   Best Email: {result['best_email']}")
    print(f"   📊 Confidence: {result['confidence']}%")
    print(f"   🌐 Found Online: {result['found_online']}")
    print(f"   💬 Reasoning: {result['reasoning'][:100]}")
    
    print("\n" + "="*70)

