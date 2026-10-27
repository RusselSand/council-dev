"""Судья исправляет ответ, который не прошёл проверку (pipeline: answer_fix.md), — для подделок
моделей: промпт правки — тот же промпт, а за ним прежний ответ и причина отказа."""

FIX = "\n\n## Your previous answer was rejected\n"


def fixing(prompt: str) -> bool:
    """Это промпт правки: судью просят исправить ответ."""
    return FIX in prompt


def task_of(prompt: str) -> str:
    """Задание, на которое отвечает модель: у правки — промпт, ответ на который не прошёл."""
    return prompt.split(FIX)[0]


def reason_of(prompt: str) -> str:
    """Причина отказа в промпте правки."""
    return prompt.split(FIX)[1].split("Reason:\n\n")[1].split("\n\nYour previous answer:")[0]


def answer_of(prompt: str) -> str:
    """Прежний ответ в промпте правки."""
    return prompt.split("Your previous answer:\n\n")[1].split("\n\nFix your answer.")[0]
