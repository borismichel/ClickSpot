import { useEffect } from "react";
import { Layout } from "antd";
import { useSearchParams } from "react-router-dom";
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
  const [searchParams, setSearchParams] = useSearchParams();
  const { messages, isLoading, sendMessage, newChat, loadMessages } = useChat();
  const {
    conversations,
    activeId,
    search,
    setSearch,
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

  useEffect(() => {
    const conversationId = searchParams.get("conversation");
    if (!conversationId || conversationId === activeId) return;
    const loadedMessages = loadConversation(conversationId);
    if (loadedMessages.length > 0) {
      loadMessages(loadedMessages);
    }
    setSearchParams({}, { replace: true });
  }, [activeId, loadConversation, loadMessages, searchParams, setSearchParams]);

  useEffect(() => {
    if (!activeId) return;
    const activeConversation = conversations.find((conversation) => conversation.id === activeId);
    if (activeConversation?.messages.length) {
      loadMessages(activeConversation.messages);
    }
  }, [activeId, conversations, loadMessages]);

  const handleNewChat = () => {
    setSearch(""); // clear any active filter so the fresh chat is visible
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
            search={search}
            onSearchChange={setSearch}
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
