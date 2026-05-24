import { useEffect } from "react";
import { Layout } from "antd";
import { usePageTitle } from "./hooks/usePageTitle";
import { useChat } from "./hooks/useChat";
import { useConversations } from "./hooks/useConversations";
import { useObjectRepo } from "./hooks/useObjectRepo";
import { ChatContainer } from "./components/chat/ChatContainer";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { AppHeader } from "./components/AppHeader";

const { Sider, Content } = Layout;

export default function App() {
  usePageTitle("Chat");
  const { messages, isLoading, sendMessage, newChat, loadMessages } = useChat();
  const {
    conversations,
    activeId,
    saveConversation,
    loadConversation,
    startNew,
    deleteConversation,
  } = useConversations();
  const { addObject } = useObjectRepo();

  // Save conversation whenever messages change (debounced by effect)
  useEffect(() => {
    if (messages.length > 0 && !isLoading) {
      saveConversation(messages);
    }
  }, [messages, isLoading, saveConversation]);

  const handleNewChat = () => {
    startNew();
    newChat();
  };

  const handleSelectConversation = (id: string) => {
    const msgs = loadConversation(id);
    if (msgs.length > 0) {
      loadMessages(msgs);
    } else {
      handleNewChat();
    }
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <AppHeader />

      <Layout>
        <Sider
          width={260}
          style={{
            background: "#fff",
            borderRight: "1px solid #f0f0f0",
            height: "calc(100vh - 64px)",
          }}
        >
          <ConversationSidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={handleSelectConversation}
            onNew={handleNewChat}
            onDelete={deleteConversation}
          />
        </Sider>

        <Content
          style={{
            height: "calc(100vh - 64px)",
            display: "flex",
            flexDirection: "column",
            background: "#fafafa",
          }}
        >
          <ChatContainer
            messages={messages}
            isLoading={isLoading}
            onSend={sendMessage}
            onSaveToRepo={addObject}
          />
        </Content>
      </Layout>

    </Layout>
  );
}
