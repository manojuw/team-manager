import logging
import streamlit as st
import os
from datetime import datetime
from teams_client import TeamsClient
from vector_store import VectorStore
from ai_assistant import ask_question, summarize_channel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

st.set_page_config(
    page_title="Teams Knowledge Base",
    page_icon="💬",
    layout="wide",
)


def init_session_state():
    defaults = {
        "teams_client": None,
        "vector_store": None,
        "connected": False,
        "teams_list": [],
        "groups_list": [],
        "channels_map": {},
        "selected_team": None,
        "selected_channels": [],
        "sync_status": {},
        "chat_history": [],
        "syncing": False,
        "auto_connect_attempted": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    if st.session_state.vector_store is None:
        try:
            st.session_state.vector_store = VectorStore()
        except Exception as e:
            st.error(f"Failed to initialize vector store: {e}")


def auto_connect_from_secrets():
    if st.session_state.connected or st.session_state.auto_connect_attempted:
        return
    st.session_state.auto_connect_attempted = True

    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    tenant_id = os.environ.get("AZURE_TENANT_ID", "")

    if not all([client_id, client_secret, tenant_id]):
        return

    try:
        client = TeamsClient(client_id, client_secret, tenant_id)
        teams = client.get_teams()
        st.session_state.teams_client = client
        st.session_state.teams_list = teams
        st.session_state.connected = True
        st.session_state.channels_map = {}
    except Exception:
        pass


def connect_to_teams():
    client_id = st.session_state.get("input_client_id", "")
    client_secret = st.session_state.get("input_client_secret", "")
    tenant_id = st.session_state.get("input_tenant_id", "")

    if not all([client_id, client_secret, tenant_id]):
        st.error("Please fill in all Azure AD credentials.")
        return

    try:
        client = TeamsClient(client_id, client_secret, tenant_id)
        teams = client.get_teams()
        st.session_state.teams_client = client
        st.session_state.teams_list = teams
        st.session_state.connected = True
        st.session_state.channels_map = {}
        st.success(f"Connected successfully! Found {len(teams)} team(s).")
    except Exception as e:
        st.error(f"Connection failed: {str(e)}")


def load_channels(team_id: str):
    if team_id in st.session_state.channels_map:
        return
    try:
        client = st.session_state.teams_client
        channels = client.get_channels(team_id)
        st.session_state.channels_map[team_id] = channels
    except Exception as e:
        st.error(f"Failed to load channels: {str(e)}")


def sync_channel(team_id: str, team_name: str, channel_id: str, channel_name: str):
    client = st.session_state.teams_client
    vs = st.session_state.vector_store

    last_sync_str = vs.get_last_sync(team_id, channel_id)
    since = None
    if last_sync_str != "Never":
        try:
            since = datetime.fromisoformat(last_sync_str)
        except (ValueError, TypeError):
            since = None

    try:
        messages = client.get_channel_messages(team_id, channel_id, since=since)
        added = vs.add_messages(messages, team_name, channel_name)
        vs.update_sync_time(team_id, channel_id)
        replies_count = sum(1 for m in messages if m.get("message_type") == "reply")
        posts_count = len(messages) - replies_count
        return added, len(messages), posts_count, replies_count
    except Exception as e:
        raise e


def sync_group(group_id: str, group_name: str):
    client = st.session_state.teams_client
    vs = st.session_state.vector_store

    sync_key = f"group-{group_id}"
    last_sync_str = vs.get_last_sync(sync_key, "conversations")
    since = None
    if last_sync_str != "Never":
        try:
            since = datetime.fromisoformat(last_sync_str)
        except (ValueError, TypeError):
            since = None

    try:
        messages = client.get_group_threads(group_id, since=since)
        added = vs.add_messages(messages, group_name, "Group Conversations")
        vs.update_sync_time(sync_key, "conversations")
        return added, len(messages)
    except Exception as e:
        raise e


def render_setup_page():
    st.header("Connect to Microsoft Teams")
    st.write(
        "Enter your Azure AD app credentials to connect to Microsoft Teams. "
        "You need an Azure AD app registration with the following API permissions:"
    )

    with st.expander("Setup Instructions", expanded=False):
        st.markdown("""
**Step 1: Register an Azure AD Application**
1. Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
2. Click "New registration"
3. Enter a name (e.g., "Teams Knowledge Base")
4. Set "Supported account types" to your organization
5. Click "Register"

**Step 2: Configure API Permissions**
1. Go to "API permissions" in your app
2. Click "Add a permission" > Microsoft Graph > Application permissions
3. Add these permissions:
   - `Team.ReadBasic.All`
   - `Channel.ReadBasic.All`
   - `ChannelMessage.Read.All`
   - `Group.Read.All`
4. Click "Grant admin consent"

**Step 3: Create a Client Secret**
1. Go to "Certificates & secrets"
2. Click "New client secret"
3. Copy the secret value (you won't see it again)

**Step 4: Get your IDs**
- **Client ID**: Found on the app's Overview page (Application ID)
- **Tenant ID**: Found on the app's Overview page (Directory ID)
        """)

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Tenant ID", key="input_tenant_id", type="password")
        st.text_input("Client ID", key="input_client_id", type="password")
    with col2:
        st.text_input("Client Secret", key="input_client_secret", type="password")

    st.button("Connect to Teams", on_click=connect_to_teams, type="primary")


def render_channel_selector():
    st.header("Select Channels to Monitor")

    teams = st.session_state.teams_list
    if not teams:
        st.warning("No teams found. Check your permissions.")
        return

    team_options = {t["name"]: t["id"] for t in teams}
    selected_team_name = st.selectbox("Select Team", options=list(team_options.keys()))

    if selected_team_name:
        team_id = team_options[selected_team_name]
        st.session_state.selected_team = {
            "id": team_id,
            "name": selected_team_name,
        }
        load_channels(team_id)

        channels = st.session_state.channels_map.get(team_id, [])
        if channels:
            st.write(f"Found {len(channels)} channel(s) in **{selected_team_name}**:")

            selected = []
            for ch in channels:
                vs = st.session_state.vector_store
                last_sync = vs.get_last_sync(team_id, ch["id"])
                label = f"{ch['name']}"
                if ch.get("description"):
                    label += f" — {ch['description']}"

                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    if st.checkbox(label, key=f"ch_{ch['id']}"):
                        selected.append(ch)
                with col2:
                    st.caption(f"Last sync: {last_sync}")
                with col3:
                    if st.button("Sync", key=f"sync_{ch['id']}"):
                        with st.spinner(f"Syncing {ch['name']}..."):
                            try:
                                added, total, posts, replies = sync_channel(
                                    team_id, selected_team_name,
                                    ch["id"], ch["name"]
                                )
                                st.success(
                                    f"Synced {ch['name']}: {added} new items added "
                                    f"({posts} posts + {replies} replies fetched)"
                                )
                            except Exception as e:
                                st.error(f"Sync failed for {ch['name']}: {str(e)}")

            st.session_state.selected_channels = selected

            if selected:
                if st.button("Sync All Selected Channels", type="primary"):
                    progress = st.progress(0)
                    total_added = 0
                    for i, ch in enumerate(selected):
                        with st.spinner(f"Syncing {ch['name']}..."):
                            try:
                                added, total, posts, replies = sync_channel(
                                    team_id, selected_team_name,
                                    ch["id"], ch["name"]
                                )
                                total_added += added
                            except Exception as e:
                                st.error(f"Failed: {ch['name']}: {str(e)}")
                        progress.progress((i + 1) / len(selected))
                    st.success(f"Sync complete! Added {total_added} new messages total.")
        else:
            st.warning("No channels found in this team.")


def render_group_selector():
    st.header("Select Groups to Sync")

    client = st.session_state.teams_client
    vs = st.session_state.vector_store

    if not st.session_state.groups_list:
        with st.spinner("Loading groups..."):
            try:
                groups = client.get_groups()
                st.session_state.groups_list = groups
            except Exception as e:
                st.error(f"Failed to load groups: {str(e)}")
                return

    groups = st.session_state.groups_list
    if not groups:
        st.info("No Microsoft 365 Groups found. Check your permissions.")
        return

    groups_only = [g for g in groups if not g.get("has_team")]
    groups_with_teams = [g for g in groups if g.get("has_team")]

    if groups_only:
        st.subheader(f"Groups ({len(groups_only)})")
        selected_groups = []
        for g in groups_only:
            sync_key = f"group-{g['id']}"
            last_sync = vs.get_last_sync(sync_key, "conversations")
            label = g["name"]
            if g.get("description"):
                label += f" — {g['description']}"

            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                if st.checkbox(label, key=f"grp_{g['id']}"):
                    selected_groups.append(g)
            with col2:
                st.caption(f"Last sync: {last_sync}")
            with col3:
                if st.button("Sync", key=f"sync_grp_{g['id']}"):
                    with st.spinner(f"Syncing {g['name']}..."):
                        try:
                            added, total = sync_group(g["id"], g["name"])
                            st.success(
                                f"Synced {g['name']}: {added} new items added "
                                f"({total} posts fetched)"
                            )
                        except Exception as e:
                            st.error(f"Sync failed for {g['name']}: {str(e)}")

        if selected_groups:
            if st.button("Sync All Selected Groups", type="primary"):
                progress = st.progress(0)
                total_added = 0
                for i, g in enumerate(selected_groups):
                    with st.spinner(f"Syncing {g['name']}..."):
                        try:
                            added, _ = sync_group(g["id"], g["name"])
                            total_added += added
                        except Exception as e:
                            st.error(f"Failed: {g['name']}: {str(e)}")
                    progress.progress((i + 1) / len(selected_groups))
                st.success(f"Sync complete! Added {total_added} new messages total.")
    else:
        st.info("No standalone Groups found (all groups are associated with Teams).")

    if groups_with_teams:
        with st.expander(f"Groups with Teams ({len(groups_with_teams)})"):
            st.caption("These groups are linked to Teams. You can sync their channels from the Channel Selector tab.")
            for g in groups_with_teams:
                st.write(f"- {g['name']}")


def render_knowledge_base():
    st.header("Knowledge Base")

    vs = st.session_state.vector_store
    stats = vs.get_stats()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Messages", stats["total_messages"])
    with col2:
        st.metric("Teams Indexed", len(stats["teams"]))
    with col3:
        st.metric("Channels Indexed", len(stats["channels"]))

    if stats["total_messages"] == 0:
        st.info("No messages indexed yet. Go to the Channel Selector tab and sync some channels first.")
        return

    st.subheader("Quick Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Generate Channel Summary"):
            with st.spinner("Generating summary..."):
                results = vs.search("project status updates decisions", n_results=30)
                if results:
                    summary = summarize_channel(results)
                    st.markdown(summary)
                else:
                    st.warning("No messages found to summarize.")
    with col2:
        if st.button("Clear Knowledge Base"):
            vs.clear_all()
            st.success("Knowledge base cleared.")
            st.rerun()


def render_chat():
    st.header("Ask About Your Projects")

    vs = st.session_state.vector_store
    stats = vs.get_stats()

    if stats["total_messages"] == 0:
        st.info("No messages indexed yet. Sync some channels first to start asking questions.")
        return

    st.write("Ask questions about project discussions, requirements, commitments, or any topic from your Teams conversations.")

    filter_team = None
    filter_channel = None
    with st.expander("Filters (optional)"):
        if stats["teams"]:
            filter_team = st.selectbox(
                "Filter by Team",
                options=["All Teams"] + stats["teams"],
            )
            if filter_team == "All Teams":
                filter_team = None
        if stats["channels"]:
            filter_channel = st.selectbox(
                "Filter by Channel",
                options=["All Channels"] + stats["channels"],
            )
            if filter_channel == "All Channels":
                filter_channel = None

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask a question about your Teams conversations..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching conversations and generating answer..."):
                filters = {}
                if filter_team:
                    filters["team"] = filter_team
                if filter_channel:
                    filters["channel"] = filter_channel

                context_results = vs.search(
                    prompt,
                    n_results=20,
                    filters=filters if filters else None,
                )

                try:
                    answer = ask_question(
                        prompt,
                        context_results,
                        st.session_state.chat_history[:-1],
                    )
                    st.markdown(answer)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": answer}
                    )
                except Exception as e:
                    error_msg = f"Sorry, I encountered an error: {str(e)}"
                    st.error(error_msg)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": error_msg}
                    )

                with st.expander("View Source Messages"):
                    for r in context_results[:10]:
                        st.caption(
                            f"**{r['metadata'].get('channel', 'N/A')}** | "
                            f"Relevance: {r['relevance']:.0%}"
                        )
                        st.text(r["content"])
                        st.divider()

    if st.session_state.chat_history:
        if st.button("Clear Chat History"):
            st.session_state.chat_history = []
            st.rerun()


def main():
    init_session_state()
    auto_connect_from_secrets()

    st.title("Teams Knowledge Base")
    st.caption("Extract, index, and query your Microsoft Teams conversations with AI")

    if not st.session_state.connected:
        render_setup_page()
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "Channel Selector",
            "Group Selector",
            "Knowledge Base",
            "Ask Questions",
        ])

        with tab1:
            render_channel_selector()
        with tab2:
            render_group_selector()
        with tab3:
            render_knowledge_base()
        with tab4:
            render_chat()

        with st.sidebar:
            st.subheader("Connection Status")
            st.success("Connected to Teams")

            stats = st.session_state.vector_store.get_stats()
            st.metric("Messages Indexed", stats["total_messages"])

            if stats["teams"]:
                st.write("**Indexed Teams:**")
                for t in stats["teams"]:
                    st.write(f"  - {t}")

            if stats["channels"]:
                st.write("**Indexed Channels:**")
                for c in stats["channels"]:
                    st.write(f"  - {c}")

            st.divider()
            if st.button("Disconnect"):
                st.session_state.connected = False
                st.session_state.teams_client = None
                st.session_state.teams_list = []
                st.session_state.groups_list = []
                st.session_state.channels_map = {}
                st.rerun()

            st.divider()
            st.caption("Powered by Microsoft Graph API & OpenAI")


if __name__ == "__main__":
    main()
