from googleapiclient.discovery import Resource
import logging

LABEL_NAME = "Processed"

logger = logging.getLogger(__name__)


def apply_label(service: Resource, message_id: str, label_id: str) -> None:
    if not label_id:
        logger.warning("Label ID not provided.")
        return

    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': [label_id]}
        ).execute()
        logger.info(f'Label "Processed" applied to message {message_id}.')
    except Exception as e:
        logger.error(f"Failed to apply label to {message_id}: {e}")


def get_label_id(service: Resource) -> str | None:
    try:
        labels = service.users().labels().list(userId='me').execute().get('labels', [])
        for label in labels:
            if label['name'].lower() == LABEL_NAME.lower():
                return label['id']
        logger.warning(f"Label '{LABEL_NAME}' not found.")
    except Exception as e:
        logger.error(f"Failed to fetch labels: {e}")
    return None
