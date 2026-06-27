import { useEffect, useState } from "react";
import { Layout, Drawer, Button, theme } from "antd";
import { UnorderedListOutlined } from "@ant-design/icons";
import { useSearchParams } from "react-router-dom";
import { usePageTitle } from "./hooks/usePageTitle";
import { useChat } from "./hooks/useChat";
import { useConversations } from "./hooks/useConversations";
import { useObjectRepo } from "./hooks/useObjectRepo";
import { useIsMobile } from "./hooks/useIsMobile";
import { ChatContainer } from "./components/chat/ChatContainer";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { AppHeader } from "./components/AppHeader";

const { Sider, Content } = Layout;

export default function App() {
  usePageTitle("Chat");
  const { token } = theme.useToken();
  const isMobile = useIsMobile(); // matchMedia-based; reliable in headless renders
  const [drawerOpen, setDrawerOpen] = useState(false);
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
      loadMessages(loadedMessages, conversationId);
    }
    setSearchParams({}, { replace: true });
  }, [activeId, loadConversation, loadMessages, searchParams, setSearchParams]);

  useEffect(() => {
    if (!activeId) return;
    const activeConversation = conversations.find((conversation) => conversation.id === activeId);
    if (activeConversation?.messages.length) {
      loadMessages(activeConversation.messages, activeId);
    }
  }, [activeId, conversations, loadMessages]);

  const handleNewChat = () => {
    setSearch(""); // clear any active filter so the fresh chat is visible
    startNew();
    newChat();
    setDrawerOpen(false); // close the mobile conversation drawer (no-op on desktop)
  };

  const handleSelectConversation = (id: string) => {
    setDrawerOpen(false); // close the mobile conversation drawer (no-op on desktop)
    const msgs = loadConversation(id);
    if (msgs.length > 0) {
      loadMessages(msgs, id);
    } else {
      handleNewChat();
    }
  };

  // One ConversationSidebar instance, hosted in the desktop Sider or — on
  // mobile, where the 260px Sider would crush the chat content — the off-canvas
  // Drawer (CLI-96).
  const sidebar = (
    <ConversationSidebar
      conversations={conversations}
      activeId={activeId}
      search={search}
      onSearchChange={setSearch}
      onSelect={handleSelectConversation}
      onNew={handleNewChat}
      onDelete={deleteConversation}
    />
  );

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <AppHeader
        leading={
          <Button
            type="text"
            icon={<UnorderedListOutlined />}
            aria-label="Open conversations"
            onClick={() => setDrawerOpen(true)}
          />
        }
      />

      <Layout>
        {isMobile ? (
          <Drawer
            placement="left"
            width={280}
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            title="Conversations"
            styles={{ body: { padding: 0 } }}
          >
            {sidebar}
          </Drawer>
        ) : (
          <Sider
            width={260}
            style={{
              background: "#fff",
              borderRight: "1px solid #f0f0f0",
              height: "calc(100vh - 64px)",
            }}
          >
            {sidebar}
          </Sider>
        )}

        <Content
          style={{
            height: "calc(100vh - 64px)",
            display: "flex",
            flexDirection: "column",
            background: token.colorBgLayout,
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
