import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Network,
  Cpu,
  X,
  Code,
  Server,
  TestTube,
  CheckCircle2,
  Mic,
} from "lucide-react";
import { Conversation } from "@elevenlabs/client";
import "./App.css";

// ─── Tree helper functions (pure) ───────────────────────────────────────────────

const updateNodeInTree = (nodes, targetId, updater) => {
  return nodes.map((node) => {
    if (node.id === targetId) return updater(node);
    if (node.children.length > 0) {
      return {
        ...node,
        children: updateNodeInTree(node.children, targetId, updater),
      };
    }
    return node;
  });
};

const addNodeToTree = (nodes, parentId, newChild) => {
  if (!parentId) {
    // No parent → add as child of root (first node)
    return nodes.map((node, i) =>
      i === 0 ? { ...node, children: [...node.children, newChild] } : node
    );
  }
  return nodes.map((node) => {
    if (node.id === parentId) {
      return { ...node, children: [...node.children, newChild] };
    }
    if (node.children.length > 0) {
      return {
        ...node,
        children: addNodeToTree(node.children, parentId, newChild),
      };
    }
    return node;
  });
};

const findNodeInTree = (nodes, targetId) => {
  for (const node of nodes) {
    if (node.id === targetId) return node;
    if (node.children.length > 0) {
      const found = findNodeInTree(node.children, targetId);
      if (found) return found;
    }
  }
  return null;
};

const teamToName = (team) => {
  switch (team) {
    case "product":
      return "Product Agent";
    case "engineering":
      return "SWE Agent";
    case "quality":
      return "QA Agent";
    default:
      return "Agent";
  }
};

const makeTimeStr = (timestamp) => {
  const date = timestamp ? new Date(timestamp * 1000) : new Date();
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

// ─── Icon helper ────────────────────────────────────────────────────────────────

const getIconForRole = (role, size = 18) => {
  if (role.includes("Manager") || role.includes("Planner"))
    return <Network size={size} />;
  if (role.includes("Product")) return <Server size={size} />;
  if (role.includes("SWE") || role.includes("Engineering"))
    return <Code size={size} />;
  if (role.includes("QA") || role.includes("Quality"))
    return <TestTube size={size} />;
  return <Cpu size={size} />;
};

// ─── AgentNode Component ────────────────────────────────────────────────────────

const AgentNode = ({ agent, onSelect }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleSelect = (e) => {
    e.stopPropagation();
    onSelect(agent.id);
  };

  return (
    <div className="tree-node-wrapper">
      <motion.div
        initial={{ opacity: 0, x: -20, scale: 0.95 }}
        animate={{ opacity: 1, x: 0, scale: 1 }}
        transition={{ duration: 0.4, type: "spring", bounce: 0.3 }}
        className={`agent-card ${agent.status === "success" ? "completed-card" : ""} ${agent.status === "failed" ? "failed-card" : ""} ${agent.status === "active" ? "active-card" : ""}`}
        onClick={handleSelect}
      >
        <div className="agent-header">
          <div className="agent-info">
            <div className="agent-icon">{getIconForRole(agent.name, 20)}</div>
            <div>
              <h3>{agent.name}</h3>
            </div>
          </div>
          <div className="agent-actions">
            <div
              className={`status-indicator ${agent.status}`}
              title={`Status: ${agent.status}`}
            ></div>
          </div>
        </div>

        <div className="agent-body">
          <p className="task-desc">{agent.task}</p>
          <div className="progress-bar-container">
            <motion.div
              className={`progress-bar ${agent.status === "success" ? "success" : ""} ${agent.status === "failed" ? "failed" : ""}`}
              initial={{ width: 0 }}
              animate={{ width: `${agent.progress}%` }}
              transition={{ duration: 0.5 }}
            ></motion.div>
          </div>
          <div className="agent-footer">
            <span className="completion-text">
              {agent.status === "success" ? (
                <CheckCircle2
                  size={12}
                  style={{
                    display: "inline",
                    verticalAlign: "-2px",
                    marginRight: "4px",
                  }}
                />
              ) : null}
              {agent.progress.toFixed(0)}%{" "}
              {agent.status === "success"
                ? "Complete"
                : agent.status === "failed"
                  ? "Failed"
                  : "Processing"}
            </span>
            {agent.children.length > 0 && (
              <span
                className="children-count"
                onClick={(e) => {
                  e.stopPropagation();
                  setIsExpanded(!isExpanded);
                }}
              >
                {agent.children.length} Tasks {isExpanded ? "▼" : "▶"}
              </span>
            )}
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {isExpanded && agent.children.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0, filter: "blur(4px)" }}
            animate={{ opacity: 1, height: "auto", filter: "blur(0px)" }}
            exit={{ opacity: 0, height: 0, filter: "blur(4px)" }}
            transition={{ duration: 0.4, type: "spring", bounce: 0.1 }}
            className="tree-children"
          >
            {agent.children.map((child) => (
              <div key={child.id} className="tree-child-wrapper">
                <AgentNode agent={child} onSelect={onSelect} />
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── ThoughtModal (Activity Log) ────────────────────────────────────────────────

const ThoughtModal = ({ agent, onClose }) => {
  if (!agent) return null;

  return (
    <motion.div
      className="modal-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="modal-content"
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 10 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              className="agent-icon"
              style={{
                padding: "6px",
                borderRadius: "6px",
                background: "#f1f5f9",
              }}
            >
              {getIconForRole(agent.name, 20)}
            </div>
            <h2>Activity Log: {agent.name}</h2>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="thoughts-container custom-scrollbar">
          {agent.thoughts.map((thought, idx) => (
            <motion.div
              key={idx}
              className="thought-item"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.05 }}
            >
              <div className="thought-time">{thought.time}</div>
              <div className="thought-content">
                <div className={`thought-status ${thought.status}`}></div>
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <p>{thought.text}</p>
                  {thought.link && (
                    <a
                      href={thought.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="thought-link"
                    >
                      Open Local Output Directory
                    </a>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
          {agent.status !== "success" && agent.status !== "failed" && (
            <motion.div
              className="thought-item cursor-blink"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: agent.thoughts.length * 0.05 }}
            >
              <div className="thought-time">Now</div>
              <div className="thought-content">
                <p>Processing next operation...</p>
              </div>
            </motion.div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
};

// ─── VoiceWaveform ──────────────────────────────────────────────────────────────

const VoiceWaveform = ({ isListening }) => {
  const bars = 30;
  const requestRef = useRef();
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!isListening) {
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
      if (containerRef.current) {
        const children = containerRef.current.children;
        for (let i = 0; i < children.length; i++) {
          children[i].style.transform = "scaleY(0.1)";
        }
      }
      return;
    }

    const initAudio = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        const audioCtx = new (
          window.AudioContext || window.webkitAudioContext
        )();
        audioContextRef.current = audioCtx;

        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        analyserRef.current = analyser;

        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);

        const animate = () => {
          analyser.getByteFrequencyData(dataArray);

          if (containerRef.current) {
            const children = containerRef.current.children;
            for (let i = 0; i < bars; i++) {
              if (children[i]) {
                const val = dataArray[i] || 0;
                const height = 5 + (val / 255) * 80;
                const scale = Math.max(height / 80, 0.1);
                children[i].style.transform = `scaleY(${scale})`;
              }
            }
          }
          requestRef.current = requestAnimationFrame(animate);
        };
        animate();
      } catch (err) {
        console.error("Error accessing microphone:", err);
      }
    };

    initAudio();

    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
      if (audioContextRef.current)
        audioContextRef.current.close().catch(() => { });
    };
  }, [isListening]);

  return (
    <div className="sound-waves" ref={containerRef}>
      {Array.from({ length: bars }).map((_, i) => (
        <div
          key={i}
          className="dynamic-wave-bar"
          style={{
            height: "80px",
            opacity: isListening ? 1 : 0.4,
            transformOrigin: "center",
            transform: "scaleY(0.1)",
          }}
        />
      ))}
    </div>
  );
};

// ─── ElevenLabs system prompt for startup spec collection ───────────────────────

const STARTUP_SPEC_PROMPT = `You are an enthusiastic and perceptive startup idea specialist having a natural conversation to deeply understand a user's project or startup idea. The details you collect will be used to actually BUILD the project with an AI engineering team, so specifics matter.

Your approach:
- Match the user's energy and excitement level — if they're fired up, match that energy. If they're thoughtful, be thoughtful.
- Ask smart, probing follow-up questions to drill into specifics
- Naturally cover: what it does, who it's for, key features, how users interact with it, technical preferences (web app, mobile, desktop, game, etc.), visual design preferences, and what makes it unique
- Ask 1-2 questions at a time — don't overwhelm, keep it conversational
- Be genuinely curious and build on what they share
- Push for specifics: "What would that screen look like?" "How would a user do X?" "What happens when..."
- Think about what an engineering team needs to know to build this
- When you have enough detail, briefly summarize what you've captured and ask if anything is missing
- Keep responses concise and high-energy`;

// ─── ConversationView ───────────────────────────────────────────────────────────

const ConversationView = ({ onComplete }) => {
  const agentId = "agent_4701kj22bj22ef3rc0sbc6qs009g";
  const [isListening, setIsListening] = useState(false);
  const [conversationStatus, setConversationStatus] = useState(
    "Tap to start a live conversation.",
  );
  const [transcript, setTranscript] = useState([]);
  const conversationRef = useRef(null);
  const transcriptRef = useRef([]);

  const startConversation = async () => {
    if (conversationRef.current) return;
    transcriptRef.current = [];
    setTranscript([]);
    try {
      setConversationStatus("Requesting microphone access...");
      await navigator.mediaDevices.getUserMedia({ audio: true });
      setConversationStatus("Connecting to ElevenLabs...");
      setIsListening(true);

      const conversation = await Conversation.startSession({
        agentId,
        connectionType: "webrtc",
        onConnect: () => setConversationStatus("Connected. You can speak."),
        onDisconnect: () => {
          conversationRef.current = null;
          setIsListening(false);
          setConversationStatus("Conversation ended.");
        },
        onError: (error) => {
          console.error("ElevenLabs conversation error:", error);
          conversationRef.current = null;
          setIsListening(false);
          setConversationStatus("Connection error.");
        },
        onStatusChange: (status) => {
          const nextStatus =
            typeof status === "string"
              ? status
              : status && typeof status === "object" && "status" in status
                ? status.status
                : JSON.stringify(status);
          const prettyStatus =
            typeof nextStatus === "string" && nextStatus.length
              ? `${nextStatus[0].toUpperCase()}${nextStatus.slice(1)}`
              : "Status update";
          setConversationStatus(prettyStatus);
        },
        onModeChange: (mode) => {
          if (mode === "speaking") {
            setConversationStatus("Agent speaking...");
          } else if (mode === "listening") {
            setConversationStatus("Listening...");
          }
        },
        onMessage: (message) => {
          console.log("ElevenLabs message:", message);
          const text =
            message?.text ||
            message?.message ||
            message?.content ||
            message?.transcript ||
            message?.data?.text ||
            message?.data?.message ||
            message?.data?.content ||
            message?.data?.transcript ||
            message?.payload?.text ||
            message?.payload?.message ||
            message?.payload?.content ||
            message?.payload?.transcript ||
            "";
          if (!text.trim()) return;
          const role =
            message?.role ||
            message?.speaker ||
            message?.type ||
            message?.data?.role ||
            message?.payload?.role ||
            "unknown";
          const entry = { role, text: text.trim() };
          const next = [...transcriptRef.current, entry];
          transcriptRef.current = next;
          setTranscript(next);
        },
      });

      conversationRef.current = conversation;
    } catch (error) {
      console.error("Failed to start conversation:", error);
      conversationRef.current = null;
      setIsListening(false);
      setConversationStatus("Microphone access denied.");
    }
  };

  const stopConversation = async () => {
    if (!conversationRef.current) {
      setIsListening(false);
      return;
    }
    try {
      await conversationRef.current.endSession();
    } catch (error) {
      console.error("Failed to end conversation:", error);
    } finally {
      conversationRef.current = null;
      setIsListening(false);
      setConversationStatus("Conversation ended.");
    }
  };

  useEffect(() => {
    return () => {
      if (conversationRef.current) {
        conversationRef.current.endSession();
        conversationRef.current = null;
      }
    };
  }, []);

  const toggleListening = () => {
    if (isListening) {
      stopConversation();
    } else {
      startConversation();
    }
  };

  const handleFinalize = async () => {
    await stopConversation();
    onComplete(transcriptRef.current);
  };

  return (
    <div className="conversation-layout">
      <div className="conversation-header">
        <h2 className="sleek-title">Start your conversation</h2>
        <p className="sleek-subtitle">
          Speak naturally about your startup idea and we'll capture everything to
          build your project.
        </p>
      </div>

      <div className="voice-container">
        <VoiceWaveform isListening={isListening} />

        <div className="mic-btn-container">
          <button
            className={`mic-btn ${isListening ? "listening" : ""}`}
            onClick={toggleListening}
          >
            <Mic size={28} />
          </button>
          <p className="voice-status">{conversationStatus}</p>
        </div>
      </div>

      <div className="chat-input-area">
        <button
          className="sleek-finalize-btn"
          onClick={handleFinalize}
          style={{ fontWeight: 200 }}
        >
          Finish Conversation
        </button>
      </div>
    </div>
  );
};

// ─── Main App ───────────────────────────────────────────────────────────────────

const WS_URL = `ws://${window.location.hostname}:8000/ws/engine`;

export default function App() {
  const [currentView, setCurrentView] = useState("conversation");
  const [jobSpec, setJobSpec] = useState("");
  const [agents, setAgents] = useState([]);
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const [engineStatus, setEngineStatus] = useState("idle");
  const wsRef = useRef(null);

  // Derive selected agent from tree for always-fresh data in modal.
  const selectedAgent = selectedAgentId
    ? findNodeInTree(agents, selectedAgentId)
    : null;

  // ─── Engine event handler ───────────────────────────────────────────────────

  const handleEngineEvent = useCallback((event) => {
    const { type, task_id, parent_id, team, description, status, data, timestamp } =
      event;
    const time = makeTimeStr(timestamp);

    switch (type) {
      case "heartbeat":
        break;

      case "engine_started":
        setAgents((prev) =>
          updateNodeInTree(prev, "planner-root", (node) => ({
            ...node,
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: "Engine initialized",
                time,
                status: "success",
              },
            ],
          }))
        );
        break;

      case "spec_created":
        setJobSpec(data?.spec || "");
        setAgents((prev) =>
          updateNodeInTree(prev, "planner-root", (node) => ({
            ...node,
            progress: Math.max(node.progress, 10),
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: "Project specification generated from conversation",
                time,
                status: "success",
              },
            ],
          }))
        );
        break;

      case "planning_iteration":
        setAgents((prev) =>
          updateNodeInTree(prev, "planner-root", (node) => ({
            ...node,
            progress: Math.min(node.progress + 5, 90),
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: `Planning iteration ${data?.iteration || "?"}`,
                time,
                status: "success",
              },
            ],
          }))
        );
        break;

      case "task_dispatched":
      case "subtask_dispatched": {
        const nodeName = teamToName(team);
        const newNode = {
          id: task_id,
          name: nodeName,
          task: description || "Processing...",
          progress: 0,
          status: "pending",
          thoughts: [
            {
              id: 0,
              text: `Dispatched to ${team || "engineering"} team`,
              time,
              status: "success",
            },
          ],
          children: [],
        };
        setAgents((prev) => {
          // If parent_id given but parent doesn't exist in tree, fall back to root.
          const effectiveParent =
            parent_id && findNodeInTree(prev, parent_id)
              ? parent_id
              : null;
          return addNodeToTree(prev, effectiveParent, newNode);
        });
        break;
      }

      case "task_started":
        setAgents((prev) =>
          updateNodeInTree(prev, task_id, (node) => ({
            ...node,
            status: "active",
            progress: Math.max(node.progress, 10),
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: "Worker started processing...",
                time,
                status: "pending",
              },
            ],
          }))
        );
        break;

      case "task_completed": {
        const isSuccess = status === "complete";
        const isFailed = status === "failed";
        setAgents((prev) =>
          updateNodeInTree(prev, task_id, (node) => ({
            ...node,
            status: isSuccess ? "success" : isFailed ? "failed" : "active",
            progress: isSuccess || isFailed ? 100 : Math.max(node.progress, 80),
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: data?.summary || `Task ${status}`,
                time,
                status: isSuccess ? "success" : "pending",
              },
            ],
          }))
        );
        break;
      }

      case "subplanner_started":
        setAgents((prev) =>
          updateNodeInTree(prev, task_id, (node) => ({
            ...node,
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: "Task is complex — decomposing into subtasks...",
                time,
                status: "pending",
              },
            ],
          }))
        );
        break;

      case "build_complete":
        setAgents((prev) =>
          updateNodeInTree(prev, "planner-root", (node) => ({
            ...node,
            progress: 100,
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: `Build complete — ${data?.tasks_completed || 0}/${data?.tasks_dispatched || 0} tasks completed`,
                time,
                status: "success",
              },
            ],
          }))
        );
        break;

      case "engine_done":
        setEngineStatus("done");
        setAgents((prev) =>
          updateNodeInTree(prev, "planner-root", (node) => ({
            ...node,
            progress: 100,
            status: "success",
            thoughts: [
              ...node.thoughts,
              {
                id: node.thoughts.length,
                text: `All done! Total time: ${data?.total_time || "?"}s, tokens: ${data?.total_tokens?.toLocaleString() || "?"}`,
                time,
                status: "success",
                link: data?.output_dir,
              },
            ],
          }))
        );
        break;

      case "error":
        setEngineStatus("error");
        console.error("Engine error:", event.message);
        break;

      default:
        console.log("Unhandled engine event:", type, event);
    }
  }, []);

  // ─── Connect to engine backend ──────────────────────────────────────────────

  const connectToEngine = useCallback(
    (transcript) => {
      setEngineStatus("connecting");

      // Create root planner node.
      setAgents([
        {
          id: "planner-root",
          name: "Manager Agent",
          task: "Analyzing conversation and planning project...",
          progress: 0,
          status: "active",
          thoughts: [
            {
              id: 0,
              text: "Engine starting, processing conversation...",
              time: makeTimeStr(),
              status: "pending",
            },
          ],
          children: [],
        },
      ]);

      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setEngineStatus("running");
        ws.send(JSON.stringify({ type: "start", conversation: transcript }));
      };

      ws.onmessage = (evt) => {
        try {
          const event = JSON.parse(evt.data);
          handleEngineEvent(event);
        } catch (err) {
          console.error("Failed to parse engine event:", err);
        }
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        setEngineStatus("error");
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    },
    [handleEngineEvent]
  );

  // ─── Animate progress for active nodes ────────────────────────────────────

  useEffect(() => {
    if (engineStatus !== "running") return;

    const tick = (nodes) =>
      nodes.map((node) => {
        let newProgress = node.progress;
        if (node.status === "active" && newProgress < 90) {
          newProgress = Math.min(newProgress + Math.random() * 1.5, 90);
        }
        return {
          ...node,
          progress: newProgress,
          children:
            node.children.length > 0 ? tick(node.children) : node.children,
        };
      });

    const interval = setInterval(() => setAgents((prev) => tick(prev)), 1500);
    return () => clearInterval(interval);
  }, [engineStatus]);

  // ─── Cleanup WebSocket on unmount ─────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // ─── Handlers ─────────────────────────────────────────────────────────────

  const handleConversationComplete = useCallback(
    (transcript) => {
      // Show transcript in spec area until spec_created event replaces it.
      const displayText = transcript
        .map((msg) => `${msg.role}: ${msg.text}`)
        .join("\n");
      setJobSpec(displayText || "Generating specification from conversation...");
      setCurrentView("visualization");
      connectToEngine(transcript);
    },
    [connectToEngine]
  );

  const handleBackToConversation = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setAgents([]);
    setJobSpec("");
    setEngineStatus("idle");
    setSelectedAgentId(null);
    setCurrentView("conversation");
  }, []);

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="app-container">
      <nav className="topbar">
        <div className="brand">
          <h1>One Call</h1>
        </div>
        {currentView === "visualization" && (
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {engineStatus === "connecting" && (
              <span className="sleek-subtitle" style={{ fontSize: "12px" }}>
                Connecting...
              </span>
            )}
            {engineStatus === "running" && (
              <span className="sleek-subtitle" style={{ fontSize: "12px" }}>
                Engine running...
              </span>
            )}
            {engineStatus === "done" && (
              <span style={{ fontSize: "12px", color: "#10b981" }}>
                Build complete
              </span>
            )}
            {engineStatus === "error" && (
              <span style={{ fontSize: "12px", color: "#ef4444" }}>
                Engine error
              </span>
            )}
            <button className="view-tab" onClick={handleBackToConversation}>
              Back to Conversation
            </button>
          </div>
        )}
      </nav>

      <main className="main-content">
        {currentView === "conversation" ? (
          <ConversationView onComplete={handleConversationComplete} />
        ) : (
          <>
            <div className="prompt-container">
              <div className="prompt-header">
                <span>Project Specification</span>
              </div>
              <div className="prompt-body">
                <div className="prompt-display custom-scrollbar">
                  {jobSpec || "Generating specification from conversation..."}
                </div>
              </div>
            </div>

            <div className="hierarchy-container">
              {agents.length > 0 ? (
                agents.map((agent) => (
                  <AgentNode
                    key={agent.id}
                    agent={agent}
                    onSelect={setSelectedAgentId}
                  />
                ))
              ) : (
                <div
                  style={{
                    textAlign: "center",
                    color: "#8b8b8d",
                    padding: "40px",
                  }}
                >
                  Connecting to engine...
                </div>
              )}
            </div>
          </>
        )}
      </main>

      <AnimatePresence>
        {selectedAgent && (
          <ThoughtModal
            agent={selectedAgent}
            onClose={() => setSelectedAgentId(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
