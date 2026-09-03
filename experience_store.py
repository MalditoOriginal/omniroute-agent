#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
experience_store.py
Локальная векторная база данных (ChromaDB) для накопления, поиска и переиспользования опыта Эволюции.
"""
import os
import json
import logging
import datetime
from typing import List, Dict, Any, Optional

class ExperienceStore:
    """
    Управляет векторной базой данных ChromaDB для семантического поиска прошлых эволюций.
    Обеспечивает graceful shutdown: если ChromaDB или модель недоступны, функционал отключается.
    """
    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "evolution_experience"):
        self.logger = logging.getLogger("ExperienceStoreLogger")
        self.client = None
        self.embedder = None
        self.collection = None
        
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=db_path)
            self.logger.info("ChromaDB PersistentClient инициализирован.")
        except Exception as e:
            self.logger.error(f"Не удалось инициализировать ChromaDB: {e}. Функционал опыта отключен.")
            return

        try:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
            self.logger.info("Модель эмбеддингов all-MiniLM-L6-v2 загружена.")
        except Exception as e:
            self.logger.error(f"Не удалось инициализировать SentenceTransformer: {e}. Функционал опыта отключен.")
            self.client = None
            return

        try:
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            self.logger.info(f"Коллекция '{collection_name}' готова к работе.")
        except Exception as e:
            self.logger.error(f"Не удалось получить/создать коллекцию '{collection_name}': {e}.")
            self.client = None
            self.embedder = None

    def _get_embedding(self, text: str) -> List[float]:
        """Генерирует вектор (list of floats) с помощью локальной модели."""
        if not self.embedder:
            return []
        return self.embedder.encode(text).tolist()

    def add_experience(self, id: str, prompt: str, evolution_code: str, status: str, metadata: dict = None) -> None:
        """
        Сохраняет запись об эволюции в БД.
        Логирует ошибки, но не прерывает основной процесс.
        """
        if not self.collection:
            self.logger.warning("ExperienceStore не активен. Пропуск add_experience.")
            return

        try:
            text_for_embedding = f"{prompt} {evolution_code}"
            embedding = self._get_embedding(text_for_embedding)
            
            if not embedding:
                self.logger.error("Не удалось сгенерировать эмбеддинг. Пропуск сохранения.")
                return

            final_metadata = {
                "status": status,
                "evolution_code": evolution_code,
                "timestamp": datetime.datetime.now().isoformat(),
                **(metadata or {})
            }

            self.collection.add(
                ids=[id],
                embeddings=[embedding],
                documents=[prompt],
                metadatas=[final_metadata]
            )
            self.logger.info(f"Опыт {id} успешно сохранен в БД.")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении опыта {id}: {e}")

    def query_experience(self, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Выполняет семантический поиск прошлых решений.
        Возвращает список словарей с найденным опытом.
        """
        if not self.collection:
            self.logger.warning("ExperienceStore не активен. Пропуск query_experience.")
            return []

        try:
            query_embedding = self._get_embedding(query_text)
            if not query_embedding:
                return []

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )

            experiences = []
            if results and results.get('documents'):
                for i, doc in enumerate(results['documents'][0]):
                    dist = results['distances'][0][i] if results.get('distances') else 1.0
                    meta = results['metadatas'][0][i] if results.get('metadatas') else {}
                    experiences.append({
                        "document": doc,
                        "metadata": meta,
                        "distance": dist
                    })
            
            self.logger.info(f"Найдено {len(experiences)} релевантных записей для запроса.")
            return experiences
        except Exception as e:
            self.logger.error(f"Ошибка при поиске опыта: {e}")
            return []

    def get_all_experiences(self) -> List[Dict[str, Any]]:
        """Возвращает все сохраненные записи из коллекции."""
        if not self.collection:
            self.logger.warning("ExperienceStore не активен. Пропуск get_all_experiences.")
            return []

        try:
            results = self.collection.get()
            experiences = []
            if results and results.get('documents'):
                for i, doc in enumerate(results['documents']):
                    meta = results['metadatas'][i] if results.get('metadatas') else {}
                    experiences.append({
                        "document": doc,
                        "metadata": meta
                    })
            return experiences
        except Exception as e:
            self.logger.error(f"Ошибка при получении всех записей: {e}")
            return []
