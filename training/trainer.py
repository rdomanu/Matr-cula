"""Entrenamiento de modelo personalizado de reconocimiento de caracteres de matriculas.

Utiliza las imagenes corregidas por el usuario para mejorar el post-procesamiento
y opcionalmente entrenar un clasificador de caracteres simple.
"""

import json
import os
from collections import Counter

import config
from training.collector import TrainingCollector


class PlateTrainer:
    """Entrena reglas de correccion basadas en las correcciones del usuario."""

    def __init__(self):
        self.collector = TrainingCollector()
        self.corrections_file = os.path.join(config.TRAINING_DIR, "corrections_map.json")
        self._correction_rules = {}
        self._load_corrections()

    def _load_corrections(self):
        """Carga reglas de correccion aprendidas."""
        if os.path.exists(self.corrections_file):
            try:
                with open(self.corrections_file, "r", encoding="utf-8") as f:
                    self._correction_rules = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._correction_rules = {}

    def _save_corrections(self):
        """Guarda reglas de correccion."""
        try:
            os.makedirs(os.path.dirname(self.corrections_file), exist_ok=True)
            with open(self.corrections_file, "w", encoding="utf-8") as f:
                json.dump(self._correction_rules, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def learn_corrections(self):
        """Analiza las correcciones del usuario y genera reglas de post-procesamiento.

        Compara ocr_text vs corrected_text para aprender patrones de error frecuentes.
        Ej: si OCR lee "O" y el usuario corrige a "0" en posiciones de digitos,
        se genera una regla de sustitucion.
        """
        dataset = self.collector.get_verified_dataset()
        if not dataset:
            return {"status": "no_data", "rules_count": 0}

        # Analizar patrones caracter a caracter
        char_substitutions = Counter()

        for image_id, info in self.collector._labels.items():
            if not info["verified"] or not info["corrected_text"]:
                continue

            ocr = info["ocr_text"] or ""
            correct = info["corrected_text"] or ""

            # Alinear caracteres (simple, misma longitud)
            min_len = min(len(ocr), len(correct))
            for i in range(min_len):
                if ocr[i] != correct[i]:
                    key = f"{ocr[i]}->{correct[i]}"
                    char_substitutions[key] += 1

        # Generar reglas con minimo 2 ocurrencias
        new_rules = {}
        for substitution, count in char_substitutions.items():
            if count >= 2:
                parts = substitution.split("->")
                if len(parts) == 2:
                    from_char, to_char = parts
                    if from_char not in new_rules:
                        new_rules[from_char] = {}
                    new_rules[from_char][to_char] = count

        self._correction_rules = new_rules
        self._save_corrections()

        return {
            "status": "success",
            "rules_count": len(new_rules),
            "rules": new_rules,
            "dataset_size": len(dataset),
        }

    def apply_learned_corrections(self, text):
        """Aplica las correcciones aprendidas a un texto OCR.

        Args:
            text: Texto crudo del OCR.

        Returns:
            Texto con correcciones aplicadas.
        """
        if not self._correction_rules or not text:
            return text

        result = list(text)
        for i, char in enumerate(result):
            if char in self._correction_rules:
                # Usar la sustitucion mas frecuente
                subs = self._correction_rules[char]
                best_sub = max(subs, key=subs.get)
                result[i] = best_sub

        return "".join(result)

    def get_correction_rules(self):
        """Obtiene las reglas de correccion actuales."""
        return self._correction_rules

    def get_training_stats(self):
        """Estadisticas de entrenamiento."""
        collector_stats = self.collector.get_stats()
        return {
            **collector_stats,
            "correction_rules": len(self._correction_rules),
            "corrections_file": self.corrections_file,
        }
