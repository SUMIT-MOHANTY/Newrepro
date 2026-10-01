import os
import json
import logging
import time
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class IPCMessage:
    def __init__(self, sender: str, recipient: str, msg_type: str, payload: Dict[str, Any]):
        self.sender = sender
        self.recipient = recipient
        self.type = msg_type
        self.payload = payload
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp
        }

class IPCRouter:
    def __init__(self, workspace_path: str):
        self.ipc_dir = os.path.join(workspace_path, '.agent_ipc')
        os.makedirs(self.ipc_dir, exist_ok=True)
        self.messages_file = os.path.join(self.ipc_dir, 'messages.json')
        if not os.path.exists(self.messages_file):
            with open(self.messages_file, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def _safe_read(self, max_retries=10) -> List[Dict]:
        for _ in range(max_retries):
            try:
                with open(self.messages_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    return json.loads(content) if content else []
            except Exception as e:
                time.sleep(0.1)
        return []

    def _safe_write(self, messages: List[Dict], max_retries=10):
        temp_file = f"{self.messages_file}.tmp"
        for _ in range(max_retries):
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(messages, f, indent=4)
                os.replace(temp_file, self.messages_file)
                return
            except Exception as e:
                time.sleep(0.1)
        logger.error("Failed to write IPC messages")

    def send_message(self, from_agent: str, to_agent: str, msg_type: str, payload: Dict[str, Any]):
        msg = IPCMessage(from_agent, to_agent, msg_type, payload)
        messages = self._safe_read()
        messages.append(msg.to_dict())
        self._safe_write(messages)
        logger.info(f"IPC: {from_agent} -> {to_agent} [{msg_type}]")

    def broadcast(self, from_agent: str, msg_type: str, payload: Dict[str, Any]):
        self.send_message(from_agent, "ALL", msg_type, payload)

    def receive_messages(self, agent_name: str) -> List[Dict]:
        all_messages = self._safe_read()
        recipient_messages = []
        
        for msg in all_messages:
            if msg.get("recipient") == agent_name or msg.get("recipient") == "ALL":
                recipient_messages.append(msg)
                
        return recipient_messages
