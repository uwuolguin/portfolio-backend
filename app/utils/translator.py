# app/utils/translator.py
"""
Product name translator with automatic fallback.
If translation fails or is identical, both fields will have the same value.
"""
from deep_translator import GoogleTranslator
import structlog
from typing import Optional, Tuple

logger = structlog.get_logger(__name__)


class ProductTranslator:
    """
    Handles automatic translation for product names.
    
    Behavior:
    - If both names provided: use as-is
    - If only one name: translate to the other language
    - If translation fails: both fields get the same value (the one provided)
    - If translation is identical: both fields get the same value
    """
    
    @staticmethod
    async def translate_product_name(
        name_es: Optional[str] = None,
        name_en: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Translates product names between Spanish and English.
        
        Args:
            name_es: Spanish product name
            name_en: English product name
            
        Returns:
            Tuple of (name_es, name_en)
            
        Raises:
            ValueError: If neither name provided
        """
        
        # Case 1: Both provided - use as-is
        if name_es and name_en:
            logger.debug("both_names_provided", name_es=name_es, name_en=name_en)
            return (name_es, name_en)
        
        # Case 2: Neither provided - error
        if not name_es and not name_en:
            raise ValueError("At least one product name (name_es or name_en) must be provided")
        
        try:
            # Case 3: Only Spanish provided - translate to English
            if name_es and not name_en:
                logger.debug("translating_es_to_en", name_es=name_es)
                
                translated_en = GoogleTranslator(source='es', target='en').translate(name_es)
                
                # Check if translation is identical (e.g., "Software" -> "Software")
                if translated_en.lower().strip() == name_es.lower().strip():
                    logger.info(
                        "translation_identical_es_to_en",
                        name=name_es,
                        reason="same_in_both_languages"
                    )
                    return (name_es, name_es)  # Both fields equal
                
                logger.info("translated_es_to_en", original=name_es, translated=translated_en)
                return (name_es, translated_en)
            
            # Case 4: Only English provided - translate to Spanish
            if name_en and not name_es:
                logger.debug("translating_en_to_es", name_en=name_en)
                
                translated_es = GoogleTranslator(source='en', target='es').translate(name_en)
                
                # Check if translation is identical
                if translated_es.lower().strip() == name_en.lower().strip():
                    logger.info(
                        "translation_identical_en_to_es",
                        name=name_en,
                        reason="same_in_both_languages"
                    )
                    return (name_en, name_en)  # Both fields equal
                
                logger.info("translated_en_to_es", original=name_en, translated=translated_es)
                return (translated_es, name_en)
        
        except Exception as e:
            logger.error("translation_failed", error=str(e), exc_info=True)
            
            # FALLBACK: If translation fails, use the same value for both
            if name_es:
                logger.warning(
                    "translation_failed_fallback",
                    using_value=name_es,
                    for_both_languages=True
                )
                return (name_es, name_es)  # Both fields equal
            else:
                logger.warning(
                    "translation_failed_fallback",
                    using_value=name_en,
                    for_both_languages=True
                )
                return (name_en, name_en)  # Both fields equal


# Convenience function for use in routers
async def get_translated_product_names(
    name_es: Optional[str] = None,
    name_en: Optional[str] = None
) -> Tuple[str, str]:
    """
    Wrapper function for easy use in FastAPI routes.
    
    Usage in router:
        name_es, name_en = await get_translated_product_names(
            name_es=product_data.name_es,
            name_en=product_data.name_en
        )
    
    Returns:
        Tuple of (name_es, name_en) - guaranteed to have both values
    """
    return await ProductTranslator.translate_product_name(name_es, name_en)