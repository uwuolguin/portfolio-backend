import httpx
import structlog
from typing import Optional, Tuple

logger = structlog.get_logger(__name__)

class UniversalTranslator:

    TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
    
    @staticmethod
    async def _translate_text(text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """
        Translate text using Google Translate free API with async httpx
        Returns None if translation fails
        """
        try:
            params = {
                'client': 'gtx',
                'sl': source_lang,
                'tl': target_lang,
                'dt': 't',
                'q': text
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(UniversalTranslator.TRANSLATE_URL, params=params)
                response.raise_for_status()
                result = response.json()
                translated = result[0][0][0]
                
                logger.info(
                    "translation_success",
                    source_lang=source_lang,
                    target_lang=target_lang,
                    original_length=len(text),
                    translated_length=len(translated)
                )
                
                return translated
                
        except httpx.TimeoutException:
            logger.warning(
                "translation_timeout",
                source_lang=source_lang,
                target_lang=target_lang,
                text_preview=text[:50]
            )
            return None
            
        except httpx.HTTPStatusError as e:
            logger.warning(
                "translation_http_error",
                status_code=e.response.status_code,
                source_lang=source_lang,
                target_lang=target_lang
            )
            return None
            
        except (KeyError, IndexError, TypeError) as e:
            logger.warning(
                "translation_parse_error",
                error=str(e),
                source_lang=source_lang,
                target_lang=target_lang
            )
            return None
            
        except Exception as e:
            logger.error(
                "translation_unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                source_lang=source_lang,
                target_lang=target_lang
            )
            return None
    
    @staticmethod
    async def translate(
        text_es: Optional[str] = None,
        text_en: Optional[str] = None,
        field_name: str = "text"
    ) -> Tuple[str, str]:
        """
        Universal translation function with fallback to duplication on failure
        
        Fallback strategy:
        1. If translation API succeeds -> return (original, translated)
        2. If translation API fails -> return (input, input) for both languages
        3. If both inputs provided -> return both as-is (no translation needed)
        """
        # Both provided - no translation needed
        if text_es and text_en:
            logger.debug(
                f"both_{field_name}_provided",
                es_length=len(text_es),
                en_length=len(text_en)
            )
            return (text_es, text_en)
        
        # Neither provided - error
        if not text_es and not text_en:
            raise ValueError(f"At least one {field_name} (Spanish or English) must be provided")
        
        # Only Spanish provided - translate to English
        if text_es and not text_en:
            logger.debug(f"translating_{field_name}_es_to_en", text=text_es[:50])
            
            translated_en = await UniversalTranslator._translate_text(text_es, 'es', 'en')
            
            # Translation failed - use Spanish text for both
            if translated_en is None:
                logger.warning(
                    f"translation_failed_using_duplicate",
                    field_name=field_name,
                    original_lang="es",
                    original_text=text_es[:50]
                )
                return (text_es, text_es)
            
            # Check if translation actually changed the text
            if translated_en.lower().strip() == text_es.lower().strip():
                logger.info(
                    f"translation_unchanged_using_original",
                    field_name=field_name,
                    text=text_es[:50]
                )
                return (text_es, text_es)
            
            return (text_es, translated_en)
        
        # Only English provided - translate to Spanish
        if text_en and not text_es:
            logger.debug(f"translating_{field_name}_en_to_es", text=text_en[:50])
            
            translated_es = await UniversalTranslator._translate_text(text_en, 'en', 'es')
            
            # Translation failed - use English text for both
            if translated_es is None:
                logger.warning(
                    f"translation_failed_using_duplicate",
                    field_name=field_name,
                    original_lang="en",
                    original_text=text_en[:50]
                )
                return (text_en, text_en)
            
            # Check if translation actually changed the text
            if translated_es.lower().strip() == text_en.lower().strip():
                logger.info(
                    f"translation_unchanged_using_original",
                    field_name=field_name,
                    text=text_en[:50]
                )
                return (text_en, text_en)
            
            return (translated_es, text_en)


async def translate_field(
    field_name: str,
    text_es: Optional[str] = None,
    text_en: Optional[str] = None
) -> Tuple[str, str]:
    """Generic translation helper for any bilingual field"""
    return await UniversalTranslator.translate(text_es, text_en, field_name=field_name)