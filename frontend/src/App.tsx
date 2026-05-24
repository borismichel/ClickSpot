import { useEffect, useState } from "react";
import { Layout, Button, Drawer, theme } from "antd";
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
  const isMobile = useIsMobile();
  const [convDrawerOpen, setConvDrawerOpen] = useState(false);
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
    setConvDrawerOpen(false); // no-op on desktop (drawer not mounted)
  };

  const handleSelectConversation = (id: string) => {
    const msgs = loadConversation(id);
    if (msgs.length > 0) {
      loadMessages(msgs);
    } else {
      handleNewChat();
    }
    setConvDrawerOpen(false);
  };

  // One sidebar instance, hosted either in the desktop Sider or the mobile drawer.
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
    <Layout style={{ minHeight: "100vh", overflowX: "hidden" }}>
      <AppHeader
        leading={
          <Button
            type="text"
            icon={<UnorderedListOutlined />}
            aria-label="Open conversations"
            onClick={() => setConvDrawerOpen(true)}
          />
        }
      />

      <Layout>
        {!isMobile && (
          <Sider
            width={260}
            style={{
              background: token.colorBgContainer,
              borderRight: `1px solid ${token.colorBorderSecondary}`,
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
            background: "#fafafa", // matches the content surface used across the other pages
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

      {isMobile && (
        <Drawer
          title="Conversations"
          placement="left"
          width={280}
          open={convDrawerOpen}
          onClose={() => setConvDrawerOpen(false)}
          styles={{ body: { padding: 0 } }}
        >
          {sidebar}
        </Drawer>
      )}
    </Layout>
  );
}
