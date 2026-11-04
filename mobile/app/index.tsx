import React, { useEffect, useRef, useState } from "react";
import {
  Alert,
  AppState,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useVideoPlayer, VideoView } from "expo-video";
import * as DocumentPicker from "expo-document-picker";
import {
  BASE,
  cache,
  cached,
  Conflict,
  Course,
  discardPending,
  openProject,
  pendingCount,
  Project,
  request,
  stage,
  Summary,
  sync,
} from "../lib/repository";

type Tab = "Home" | "Courses" | "Rounds" | "Videos" | "Profile";
const C = {
  bg: "#0b1117",
  panel: "#14222b",
  line: "#2a3e48",
  text: "#e5f0f3",
  muted: "#8da4af",
  accent: "#2cc6b5",
};
function Button({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={css.button}>
      <Text style={css.buttonText}>{label}</Text>
    </Pressable>
  );
}
function Video({ project }: { project: Project }) {
  const [time, setTime] = useState(0),
    [width, setWidth] = useState(300);
  const player = useVideoPlayer(
    project.video ? `${BASE}/projects/${project.id}/video` : null,
  );
  useEffect(() => {
    const timer = setInterval(() => setTime(player.currentTime), 100);
    return () => clearInterval(timer);
  }, [player]);
  if (!project.video) return null;
  const v = project.video;
  const height = (width * v.height) / v.width;
  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      <View style={{ height }}>
        <VideoView
          player={player}
          style={{ width: "100%", height }}
          nativeControls
          contentFit="contain"
        />
        {project.overlays
          ?.filter((o) => o.visible && o.start <= time && time < o.end)
          .map((o) => (
            <Image
              key={o.id}
              source={{
                uri: `${BASE}/projects/${project.id}/overlays/${o.id}.png?r=${project.revision}`,
              }}
              style={{
                position: "absolute",
                left: o.style!.x! * width,
                top: o.style!.y! * height,
                width: o.style!.width! * width,
                height: o.style!.height! * height,
              }}
            />
          ))}
      </View>
      <Text style={css.muted}>
        {time.toFixed(1)} s / {v.duration.toFixed(1)} s
      </Text>
    </View>
  );
}
export default function App() {
  const [tab, setTab] = useState<Tab>("Home"),
    [items, setItems] = useState<{ id: string; name: string }[]>([]),
    [courses, setCourses] = useState<Course[]>([]),
    [data, setData] = useState<Summary | null>(null),
    [status, setStatus] = useState("Connecting…"),
    [error, setError] = useState(""),
    [hole, setHole] = useState(1),
    [query, setQuery] = useState(""),
    [jobs, setJobs] = useState<
      { id: string; project_id: string; status: string; progress: number }[]
    >([]);
  const current = useRef<Summary | null>(null);
  const busy = useRef(false);
  const queue = useRef(Promise.resolve());
  function update(d: Summary) {
    current.current = d;
    setData(d);
  }
  function fail(e: unknown) {
    setError(String(e));
    setStatus(
      e instanceof Conflict
        ? "Conflict · edits retained"
        : "Offline / action failed",
    );
  }
  async function refresh() {
    try {
      await queue.current;
      await sync();
      const p = await request<typeof items>("/projects");
      setItems(p);
      await cache("projects", p);
      const c = await request<{ items: Course[] }>("/courses");
      setCourses(c.items);
      await cache("courses", c.items);
      if (current.current)
        update(await openProject(current.current.project.id));
      setStatus("Synced");
      setError("");
    } catch (e) {
      fail(e);
    }
  }
  async function choose(id: string) {
    try {
      update(await openProject(id));
      await cache("last", id);
      setTab("Rounds");
    } catch (e) {
      fail(e);
    }
  }
  function edit(fn: (p: Project) => void) {
    queue.current = queue.current
      .catch(() => {})
      .then(async () => {
        if (!current.current) return;
        const next = JSON.parse(JSON.stringify(current.current)) as Summary;
        fn(next.project);
        await stage(next.project);
        update(next);
        setStatus("Pending sync · totals update after sync");
      });
    queue.current.catch(fail);
  }
  useEffect(() => {
    (async () => {
      setItems((await cached<typeof items>("projects")) || []);
      setCourses((await cached<Course[]>("courses")) || []);
      const id = await cached<string>("last");
      if (id) update(await openProject(id));
      await refresh();
    })().catch(fail);
    const timer = setInterval(() => {
      if (!busy.current) {
        busy.current = true;
        refresh().finally(() => (busy.current = false));
      }
    }, 15000);
    const sub = AppState.addEventListener("change", (v) => {
      if (v === "active") refresh();
    });
    return () => {
      clearInterval(timer);
      sub.remove();
    };
  }, []);
  useEffect(() => {
    if (tab !== "Videos") return;
    const timer = setInterval(
      () =>
        request<typeof jobs>("/jobs")
          .then(setJobs)
          .catch(() => {}),
      2000,
    );
    return () => clearInterval(timer);
  }, [tab]);
  async function create() {
    try {
      const d = await request<Summary>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: "New round" }),
      });
      update(d);
      await cache("last", d.project.id);
      await refresh();
      setTab("Rounds");
    } catch (e) {
      fail(e);
    }
  }
  async function importVideo() {
    if (!data) return;
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: "video/*",
        copyToCacheDirectory: true,
      });
      if (result.canceled) return;
      const f = result.assets[0];
      const form = new FormData();
      form.append("file", {
        uri: f.uri,
        name: f.name,
        type: f.mimeType || "video/mp4",
      } as unknown as Blob);
      setStatus("Uploading…");
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/projects/${data.project.id}/video`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable)
          setStatus(`Uploading ${Math.round((e.loaded / e.total) * 100)}%`);
      };
      xhr.onload = () => {
        if (xhr.status < 300) {
          update(JSON.parse(xhr.responseText));
          setStatus("Uploaded");
        } else fail(xhr.responseText);
      };
      xhr.onerror = () =>
        fail("Upload interrupted. Pick the video again to retry.");
      xhr.send(form);
    } catch (e) {
      fail(e);
    }
  }
  async function apply(c: Course, teeId: string) {
    if (!data) return;
    Alert.alert(
      "Replace course?",
      "Existing scores are preserved. Round course values will be replaced.",
      [
        { text: "Cancel" },
        {
          text: "Apply",
          onPress: () => {
            (async () => {
              await queue.current;
              await sync();
              const latest = await openProject(data.project.id);
              const d = await request<Summary>(
                `/projects/${data.project.id}/course`,
                {
                  method: "POST",
                  body: JSON.stringify({
                    course_id: c.id,
                    tee_id: teeId,
                    revision: latest.project.revision,
                    confirm_replace: true,
                  }),
                },
              );
              update(d);
              await cache("project:" + d.project.id, d);
              setTab("Rounds");
            })().catch(fail);
          },
        },
      ],
    );
  }
  async function addShot() {
    const p = current.current?.project;
    if (!p?.video) return Alert.alert("Import a video first");
    const existing = p.shots || [],
      start = Math.max(0, ...existing.map((s) => s.end)),
      end = Math.min(p.video.duration, start + 5);
    if (end <= start)
      return Alert.alert(
        "No space remains",
        "Adjust the existing shot timing on the web.",
      );
    const shotId = `s${Date.now()}`;
    edit((p) => {
      p.shots!.push({
        id: shotId,
        hole,
        club: "Driver",
        start,
        end,
        distance: null,
        remaining: null,
        result: "",
        notes: "",
      });
      p.overlays!.push({
        id: `o${Date.now()}`,
        type: "shot",
        shot_id: shotId,
        start,
        end,
        visible: true,
        style: {
          x: 0.04,
          y: 0.68,
          width: 0.42,
          height: 0.25,
          background: "#101c26",
          color: "#ffffff",
          accent: "#29c4b5",
          opacity: 0.9,
          overlay_opacity: 1,
          radius: 14,
          font_size: 24,
          font: "sans",
          panel: true,
          show_course: true,
        },
      });
    });
  }
  const p = data?.project,
    hs = p?.round?.holes || [];
  return (
    <SafeAreaView style={css.safe}>
      <View style={css.header}>
        <Text style={css.logo}>⚑ Golf Video Studio</Text>
        <Text style={css.status}>{status}</Text>
      </View>
      <ScrollView
        contentContainerStyle={css.content}
        keyboardShouldPersistTaps="handled"
      >
        {error ? (
          <Text selectable style={css.error}>
            {error}
          </Text>
        ) : null}
        {tab === "Home" && (
          <>
            <Text style={css.title}>Your round. Your story.</Text>
            <Button label="＋ New round" onPress={create} />
            <Button label="↻ Synchronize" onPress={refresh} />
            <Text style={css.heading}>Projects</Text>
            {items.map((item) => (
              <Pressable
                key={item.id}
                style={css.card}
                onPress={() => choose(item.id)}
              >
                <Text style={css.cardTitle}>{item.name}</Text>
                <Text style={css.muted}>Continue editing ↗</Text>
              </Pressable>
            ))}
          </>
        )}
        {tab === "Courses" && (
          <>
            <Text style={css.title}>Course library</Text>
            <TextInput
              placeholder="Search name, city, state"
              placeholderTextColor={C.muted}
              style={css.input}
              value={query}
              onChangeText={setQuery}
            />
            <Text style={css.muted}>
              Saved manual / authorized imports. Automated USGA integration is
              not configured.
            </Text>
            <Button
              label="Open official USGA lookup ↗"
              onPress={() =>
                Linking.openURL("https://ncrdb.usga.org/courseTeeInfo.aspx")
              }
            />
            {courses
              .filter((c) =>
                `${c.name} ${c.city} ${c.state}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map((c) => (
                <View style={css.card} key={c.id}>
                  <Text style={css.cardTitle}>{c.name}</Text>
                  <Text style={css.muted}>
                    {c.city} {c.state} · {c.verification}
                  </Text>
                  {c.tees.map((tee) => (
                    <Button
                      key={tee.id}
                      label={`${tee.name} · ${tee.category} · ${tee.rating ?? "—"} / ${tee.slope ?? "—"}`}
                      onPress={() => apply(c, tee.id!)}
                    />
                  ))}
                </View>
              ))}
          </>
        )}
        {tab === "Rounds" && p && (
          <>
            <Text style={css.title}>{p.round?.course || p.name}</Text>
            <TextInput
              key={p.id + "player"}
              defaultValue={p.round?.player}
              placeholder="Player name"
              placeholderTextColor={C.muted}
              style={css.input}
              onEndEditing={(e) => {
                const v = e.nativeEvent.text;
                edit((p) => (p.round!.player = v));
              }}
            />
            <Text style={css.muted}>
              Server totals · Front {data?.totals.front.score ?? "—"} / Back{" "}
              {data?.totals.back.score ?? "—"} / Total{" "}
              {data?.totals.all.score ?? "—"} / Relative{" "}
              {data?.totals.all.relative ?? "—"}
            </Text>
            <View style={css.holes}>
              {hs.map((h) => (
                <Pressable
                  key={h.number}
                  onPress={() => setHole(h.number)}
                  style={[css.hole, hole === h.number && css.holeSelected]}
                >
                  <Text style={css.text}>{h.number}</Text>
                  <Text style={css.muted}>{h.score ?? "—"}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={css.heading}>Hole {hole}</Text>
            {(["par", "yardage", "score"] as const).map((key) => (
              <View key={key}>
                <Text style={css.muted}>{key.toUpperCase()}</Text>
                <TextInput
                  key={`${p.id}-${hole}-${key}`}
                  defaultValue={String(hs[hole - 1]?.[key] ?? "")}
                  keyboardType="number-pad"
                  placeholder="Unknown"
                  placeholderTextColor={C.muted}
                  style={css.input}
                  onEndEditing={(e) => {
                    const text = e.nativeEvent.text;
                    edit(
                      (p) =>
                        (p.round!.holes![hole - 1][key] =
                          text === "" ? null : Number(text)),
                    );
                  }}
                />
              </View>
            ))}
            <View style={css.row}>
              <Button
                label="← Previous"
                onPress={() => setHole(Math.max(1, hole - 1))}
              />
              <Button
                label="Next →"
                onPress={() => setHole(Math.min(18, hole + 1))}
              />
            </View>
            <Text style={css.heading}>Shots</Text>
            {p.shots
              ?.filter((s) => s.hole === hole)
              .map((s, i) => (
                <View key={s.id} style={css.card}>
                  <Text style={css.cardTitle}>
                    Shot {s.number ?? i + 1} · {s.club}
                  </Text>
                  <TextInput
                    defaultValue={String(s.number ?? "")}
                    accessibilityLabel="Shot number"
                    placeholder="Shot number (blank = automatic)"
                    placeholderTextColor={C.muted}
                    keyboardType="number-pad"
                    style={css.input}
                    onEndEditing={(e) => {
                      const value = e.nativeEvent.text;
                      edit(
                        (p) =>
                          (p.shots!.find((x) => x.id === s.id)!.number =
                            value === "" ? null : Number(value)),
                      );
                    }}
                  />
                  <TextInput
                    defaultValue={s.club}
                    style={css.input}
                    onEndEditing={(e) => {
                      const v = e.nativeEvent.text;
                      edit(
                        (p) => (p.shots!.find((x) => x.id === s.id)!.club = v),
                      );
                    }}
                  />
                  {(["distance", "remaining"] as const).map((key) => (
                    <TextInput
                      key={key}
                      defaultValue={String(s[key] ?? "")}
                      placeholder={`${key} (yds)`}
                      placeholderTextColor={C.muted}
                      style={css.input}
                      keyboardType="decimal-pad"
                      onEndEditing={(e) => {
                        const v = e.nativeEvent.text;
                        edit(
                          (p) =>
                            (p.shots!.find((x) => x.id === s.id)![key] =
                              v === "" ? null : Number(v)),
                        );
                      }}
                    />
                  ))}
                </View>
              ))}
            <Button label="＋ Add timed shot" onPress={addShot} />
            <Button label="Save & synchronize" onPress={refresh} />
          </>
        )}
        {tab === "Videos" && p && (
          <>
            <Text style={css.title}>Video workspace</Text>
            {p.video ? (
              <Video project={p} />
            ) : (
              <Button label="Import device video" onPress={importVideo} />
            )}
            <Text style={css.muted}>
              Use the web editor for overlay design and detailed timing. This
              client previews the same saved graphics.
            </Text>
            <Button
              label="Render MP4 on backend"
              onPress={() => {
                (async () => {
                  await queue.current;
                  await sync();
                  const latest = await openProject(p.id);
                  await request(`/projects/${p.id}/exports`, {
                    method: "POST",
                    body: JSON.stringify({
                      revision: latest.project.revision,
                      quality: "high",
                      resolution: "source",
                    }),
                  });
                  setStatus("Export queued");
                })().catch(fail);
              }}
            />
            {jobs
              .filter((j) => j.project_id === p.id)
              .map((j) => (
                <View key={j.id} style={css.card}>
                  <Text style={css.text}>
                    {j.status} · {Math.round(j.progress * 100)}%
                  </Text>
                  {j.status === "done" && (
                    <Button
                      label="Open MP4 download ↗"
                      onPress={() =>
                        Linking.openURL(`${BASE}/jobs/${j.id}/download`)
                      }
                    />
                  )}
                </View>
              ))}
          </>
        )}
        {tab === "Profile" && (
          <>
            <Text style={css.title}>Local development</Text>
            <Text style={css.muted}>
              No cloud account is configured. The backend stays on loopback. iOS
              simulator and Android adb reverse can use the shared local
              database. Production authentication, HTTPS storage and device
              builds are pending.
            </Text>
            <Button label="Synchronize pending changes" onPress={refresh} />
            <Button
              label="Check pending changes"
              onPress={() =>
                pendingCount().then((n) =>
                  Alert.alert("Pending projects", String(n)),
                )
              }
            />
            {p && (
              <Button
                label="Discard local draft & reload server"
                onPress={() =>
                  Alert.alert(
                    "Discard local draft?",
                    "Only this device’s unsynced edits will be removed.",
                    [
                      { text: "Cancel" },
                      {
                        text: "Discard",
                        style: "destructive",
                        onPress: () =>
                          discardPending(p.id).then(update).catch(fail),
                      },
                    ],
                  )
                }
              />
            )}
          </>
        )}
        {!p && tab !== "Home" && tab !== "Courses" && tab !== "Profile" && (
          <Text style={css.muted}>Choose or create a project from Home.</Text>
        )}
      </ScrollView>
      <View style={css.nav}>
        {(["Home", "Courses", "Rounds", "Videos", "Profile"] as Tab[]).map(
          (key) => (
            <Pressable
              key={key}
              onPress={() => setTab(key)}
              style={css.navItem}
            >
              <Text style={[css.navText, tab === key && { color: C.accent }]}>
                {key}
              </Text>
            </Pressable>
          ),
        )}
      </View>
    </SafeAreaView>
  );
}
const css = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { padding: 20, borderBottomWidth: 1, borderColor: C.line },
  logo: { color: C.text, fontSize: 21, fontWeight: "700" },
  status: { fontSize: 11, color: C.accent, marginTop: 8 },
  content: { padding: 20, paddingBottom: 40, gap: 12 },
  title: { color: C.text, fontSize: 30, fontWeight: "600", marginVertical: 15 },
  heading: { fontSize: 19, color: C.text, marginTop: 20 },
  card: {
    backgroundColor: C.panel,
    borderRadius: 12,
    padding: 18,
    gap: 12,
    borderWidth: 1,
    borderColor: C.line,
  },
  cardTitle: { color: C.text, fontSize: 17, fontWeight: "600" },
  muted: { color: C.muted, fontSize: 12, lineHeight: 20 },
  text: { color: C.text },
  button: {
    padding: 15,
    borderRadius: 8,
    backgroundColor: C.accent,
    alignItems: "center",
    marginVertical: 3,
  },
  buttonText: { color: "#092c29", fontSize: 14, fontWeight: "700" },
  input: {
    borderWidth: 1,
    borderColor: C.line,
    color: C.text,
    backgroundColor: C.panel,
    borderRadius: 8,
    padding: 15,
    fontSize: 17,
  },
  nav: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderColor: C.line,
    paddingVertical: 18,
  },
  navItem: { flex: 1, alignItems: "center", paddingVertical: 7 },
  navText: { color: C.muted, fontSize: 11 },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  holes: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginVertical: 18 },
  hole: {
    width: 48,
    height: 65,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 7,
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  holeSelected: { borderColor: C.accent, backgroundColor: "#193a35" },
  error: {
    color: "#ffba9e",
    fontSize: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: "#65453a",
  },
});
