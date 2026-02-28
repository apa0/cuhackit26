export async function sendChatMessage(message: string): Promise<string> {
  const res = await fetch("http://localhost:5000/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data?.error || "Chat request failed");
  }

  return data.reply;
}