import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Network,
  Activity,
  Cpu,
  X,
  Plus,
  Terminal,
  Hexagon,
  Code,
  Server,
  TestTube,
  CheckCircle2,
  ArrowRight,
  MessageSquare,
  Mic,
} from "lucide-react";
import { Conversation } from "@elevenlabs/client";
import "./App.css";

const THOUGHT_TEMPLATES = {
  Manager: [
    "Parsing user intent from The Final Prompt...",
    "Extracting core functional requirements...",
    "Drafting feature specification document...",
    "Identifying edge cases in user flow...",
    "Allocating tasks for Architect phase...",
  ],
  Architect: [
    "Evaluating tech stack alternatives...",
    "Designing microservices topology...",
    "Scaffolding optimal file structure...",
    "Defining database schemas and relations...",
    "Establishing API contracts for SWEs...",
  ],
  SWE: [
    "Writing boilerplate implementations...",
    "Implementing core algorithmic logic...",
    "Refactoring component state machine...",
    "Resolving asynchronous race conditions...",
    "Committing optimized code blocks...",
  ],
  QA: [
    "Generating unit test coverage...",
    "Running end-to-end integration tests...",
    "Simulating high-concurrency load...",
    "Identifying memory leak in sub-process...",
    "Verifying security compliance...",
  ],
};

const getThoughtsForRole = (role) => {
  let templates;
  if (role.includes("Manager")) templates = THOUGHT_TEMPLATES.Manager;
  else if (role.includes("Architect")) templates = THOUGHT_TEMPLATES.Architect;
  else if (role.includes("SWE")) templates = THOUGHT_TEMPLATES.SWE;
  else if (role.includes("QA")) templates = THOUGHT_TEMPLATES.QA;
  else templates = THOUGHT_TEMPLATES.SWE;

  const count = Math.floor(Math.random() * 4) + 2;
  return Array.from({ length: count }, (_, i) => ({
    id: i,
    text: templates[Math.floor(Math.random() * templates.length)],
    time: new Date(Date.now() - Math.random() * 10000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
    status: Math.random() > 0.2 ? "success" : "pending",
  }));
};

const getIconForRole = (role, size = 18) => {
  if (role.includes("Manager")) return <Network size={size} />;
  if (role.includes("Architect")) return <Server size={size} />;
  if (role.includes("SWE")) return <Code size={size} />;
  if (role.includes("QA")) return <TestTube size={size} />;
  return <Cpu size={size} />;
};

const AgentNode = ({ agent, onSelect, onAddChild }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleSelect = (e) => {
    e.stopPropagation();
    onSelect(agent);
  };

  const handleAddChild = (e) => {
    e.stopPropagation();
    onAddChild(agent.id, agent.name);
  };

  return (
    <div className="tree-node-wrapper">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className={`agent-card ${agent.status === "success" ? "completed-card" : ""}`}
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
              className={`progress-bar ${agent.status === "success" ? "success" : ""}`}
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
              {agent.status === "success" ? "Complete" : "Processing"}
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
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="tree-children"
          >
            {agent.children.map((child) => (
              <div key={child.id} className="tree-child-wrapper">
                <AgentNode
                  agent={child}
                  onSelect={onSelect}
                  onAddChild={onAddChild}
                />
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

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
                <p>{thought.text}</p>
              </div>
            </motion.div>
          ))}
          {agent.status !== "success" && (
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

const generateId = () => Math.random().toString(16).substring(2, 8);

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
        analyser.fftSize = 64; // Small sample size for smooth 30 bars
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
        audioContextRef.current.close().catch(() => {});
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

const ConversationView = ({ onComplete }) => {
  const agentId = "agent_0701kj1g8xppe1p9yzyqz8kevtmf";
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
            "";
          const prefix = role ? `${role}: ` : "";
          const next = [...transcriptRef.current, `${prefix}${text}`];
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
    // Mock summary until Manager Agent returns the real spec
    const transcriptText = transcriptRef.current.length
      ? transcriptRef.current.map((line) => `- ${line}`).join("\n")
      : "";
    const spec = transcriptText;
    onComplete(spec);
  };

  return (
    <div className="conversation-layout">
      <div className="conversation-header">
        <h2 className="sleek-title">Start your conversation</h2>
        <p className="sleek-subtitle">
          Speak naturally and we’ll capture the transcript to power your Project
          Specification.
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

export default function App() {
  const [currentView, setCurrentView] = useState("conversation");
  const [jobSpec, setJobSpec] = useState("");
  const [isProcessing] = useState(true);

  const [agents, setAgents] = useState([
    {
      id: generateId(),
      name: "Manager Agent",
      task: "Identifying functional requirements and extracting core features from The Final Prompt.",
      progress: 85.0,
      status: "active",
      thoughts: getThoughtsForRole("Manager"),
      children: [
        {
          id: generateId(),
          name: "Architect Agent",
          task: "Designing tech stack, architecture, and scaffolding file structure.",
          progress: 54.2,
          status: "active",
          thoughts: getThoughtsForRole("Architect"),
          children: [
            {
              id: generateId(),
              name: "SWE Lead",
              task: "Decomposing architecture into parallel tasks and delegating to SWEs.",
              progress: 30.5,
              status: "active",
              thoughts: getThoughtsForRole("SWE Lead"),
              children: [
                {
                  id: generateId(),
                  name: "SWE Node A",
                  task: "Implementing core physics engine logic.",
                  progress: 15.0,
                  status: "active",
                  thoughts: getThoughtsForRole("SWE Node Alpha"),
                  children: [],
                },
                {
                  id: generateId(),
                  name: "SWE Node B",
                  task: "Building WebGL rendering pipeline hooks.",
                  progress: 8.2,
                  status: "active",
                  thoughts: getThoughtsForRole("SWE Node Beta"),
                  children: [],
                },
              ],
            },
            {
              id: generateId(),
              name: "QA Lead",
              task: "Developing testing matrices and monitoring SWE outputs.",
              progress: 12.0,
              status: "pending",
              thoughts: getThoughtsForRole("QA Lead"),
              children: [],
            },
          ],
        },
      ],
    },
  ]);

  const [selectedAgent, setSelectedAgent] = useState(null);

  const addChild = (nodes, parentId, parentName) => {
    return nodes.map((node) => {
      if (node.id === parentId) {
        let childName =
          "SWE Node " +
          String.fromCharCode(65 + Math.floor(Math.random() * 26));
        let childTask = "Executing parallel software engineering objective...";

        const newChild = {
          id: generateId(),
          name: childName,
          task: childTask,
          progress: 0,
          status: "pending",
          thoughts: getThoughtsForRole(childName),
          children: [],
        };
        return { ...node, children: [...node.children, newChild] };
      }
      if (node.children.length > 0) {
        return {
          ...node,
          children: addChild(node.children, parentId, parentName),
        };
      }
      return node;
    });
  };

  const handleAddChild = (parentId, parentName) => {
    setAgents((prev) => addChild(prev, parentId, parentName));
  };

  useEffect(() => {
    if (!isProcessing) return;

    const updateProgress = (nodes) => {
      return nodes.map((node) => {
        let increment = 0;
        if (node.status === "active") {
          increment = Math.random() * 2.5;
        }

        let newProgress = Math.min(node.progress + increment, 100);
        let newStatus = node.status;

        if (newProgress >= 100) {
          newProgress = 100;
          newStatus = "success";
        } else if (newStatus === "pending" && Math.random() > 0.8) {
          newStatus = "active";
        }

        return {
          ...node,
          progress: newProgress,
          status: newStatus,
          children:
            node.children.length > 0 ? updateProgress(node.children) : [],
        };
      });
    };

    const interval = setInterval(() => {
      setAgents((prev) => updateProgress(prev));
    }, 1000);

    return () => clearInterval(interval);
  }, [isProcessing]);

  return (
    <div className="app-container">
      <nav className="topbar">
        <div className="brand">
          <h1>The Final Prompt</h1>
        </div>
        {currentView === "visualization" && (
          <button
            className="view-tab"
            onClick={() => setCurrentView("conversation")}
          >
            Back to Conversation
          </button>
        )}
      </nav>

      <main className="main-content">
        {currentView === "conversation" ? (
          <ConversationView
            onComplete={(spec) => {
              setJobSpec(spec);
              setCurrentView("visualization");
            }}
          />
        ) : (
          <>
            <div className="prompt-container">
              <div className="prompt-header">
                <span>Project Specification</span>
              </div>
              <div className="prompt-body">
                <div className="prompt-display custom-scrollbar">{jobSpec}</div>
              </div>
              <div style={{ marginTop: "12px", textAlign: "center" }}>
                <span className="sleek-subtitle">Repo:</span>{" "}
                <a
                  className="sleek-subtitle"
                  href="https://github.com/example/project-repo"
                  target="_blank"
                  rel="noreferrer"
                >
                  github.com/example/project-repo
                </a>
              </div>
            </div>

            <div className="hierarchy-container">
              {agents.map((agent) => (
                <AgentNode
                  key={agent.id}
                  agent={agent}
                  onSelect={setSelectedAgent}
                  onAddChild={handleAddChild}
                />
              ))}
            </div>
          </>
        )}
      </main>

      <AnimatePresence>
        {selectedAgent && (
          <ThoughtModal
            agent={selectedAgent}
            onClose={() => setSelectedAgent(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
