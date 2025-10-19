import httpx
import structlog
from typing import Optional, Tuple

logger = structlog.get_logger(__name__)

class UniversalTranslator:

    TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
    
    @staticmethod
    async def _translate_text(text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using Google Translate free API with async httpx"""
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
            return result[0][0][0]
    
    @staticmethod
    async def translate(
        text_es: Optional[str] = None,
        text_en: Optional[str] = None,
        field_name: str = "text"
    ) -> Tuple[str, str]:
        """Universal translation function"""
        if text_es and text_en:
            logger.debug(f"both_{field_name}_provided", es_length=len(text_es), en_length=len(text_en))
            return (text_es, text_en)
        
        if not text_es and not text_en:
            raise ValueError(f"At least one {field_name} (Spanish or English) must be provided")
        
        try:
            if text_es and not text_en:
                logger.debug(f"translating_{field_name}_es_to_en", text=text_es[:50])
                translated_en = await UniversalTranslator._translate_text(text_es, 'es', 'en')
                if translated_en.lower().strip() == text_es.lower().strip():
                    return (text_es, text_es)
                return (text_es, translated_en)
            
            if text_en and not text_es:
                logger.debug(f"translating_{field_name}_en_to_es", text=text_en[:50])
                translated_es = await UniversalTranslator._translate_text(text_en, 'en', 'es')
                if translated_es.lower().strip() == text_en.lower().strip():
                    return (text_en, text_en)
                return (translated_es, text_en)
        
        except Exception as e:
            logger.error(f"{field_name}_translation_error", error=str(e), exc_info=True)
            return (text_es or text_en, text_es or text_en)


async def translate_field(
    field_name: str,
    text_es: Optional[str] = None,
    text_en: Optional[str] = None
) -> Tuple[str, str]:
    """Generic translation helper for any bilingual field"""
    return await UniversalTranslator.translate(text_es, text_en, field_name=field_name)
