from abc import ABC, abstractmethod

class DocumentExtractionService(ABC):
    @abstractmethod
    def extract_text(self, document: bytes, filename: str) -> str:
        pass