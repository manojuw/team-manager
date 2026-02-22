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
        "vector_store": None,
        "groups_list": [],
        "users_list": [],
        "channels_map": {},
        "selected_team": None,
        "selected_channels": [],
        "sync_status": {},
        "chat_history": [],
        "syncing": False,
        "current_project": None,
        "project_teams_client": None,
        "project_teams_list": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    if st.session_state.vector_store is None:
        try:
            st.session_state.vector_store = VectorStore()
        except Exception as e:
            st.error(f"Failed to initialize vector store: {e}")


def get_current_project_id():
    proj = st.session_state.current_project
    return proj["id"] if proj else None


def get_teams_source_for_project(project_id: str):
    vs = st.session_state.vector_store
    sources = vs.get_data_sources(project_id)
    for src in sources:
        if src["source_type"] == "microsoft_teams":
            return src
    return None


def get_teams_client_for_project():
    project = st.session_state.current_project
    if not project:
        return None

    source = get_teams_source_for_project(project["id"])
    if not source:
        return None

    config = source.get("config", {})
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    tenant_id = config.get("tenant_id", "")

    if not all([client_id, client_secret, tenant_id]):
        return None

    cache_key = f"teams_client_{project['id']}"
    if st.session_state.get(cache_key):
        return st.session_state[cache_key]

    try:
        client = TeamsClient(client_id, client_secret, tenant_id)
        st.session_state[cache_key] = client
        return client
    except Exception:
        return None


def is_project_connected():
    project = st.session_state.current_project
    if not project:
        return False
    source = get_teams_source_for_project(project["id"])
    if not source:
        return False
    config = source.get("config", {})
    return all([config.get("client_id"), config.get("client_secret"), config.get("tenant_id")])


def load_channels(team_id: str):
    if team_id in st.session_state.channels_map:
        return
    try:
        client = get_teams_client_for_project()
        if not client:
            return
        channels = client.get_channels(team_id)
        st.session_state.channels_map[team_id] = channels
    except Exception as e:
        st.error(f"Failed to load channels: {str(e)}")


def sync_channel(team_id: str, team_name: str, channel_id: str, channel_name: str):
    client = get_teams_client_for_project()
    if not client:
        raise Exception("Teams client unavailable. Check your credentials in the Data Sources tab.")
    vs = st.session_state.vector_store
    project_id = get_current_project_id()

    last_sync_str = vs.get_last_sync(team_id, channel_id, project_id=project_id)
    since = None
    if last_sync_str != "Never":
        try:
            since = datetime.fromisoformat(last_sync_str)
        except (ValueError, TypeError):
            since = None

    try:
        messages = client.get_channel_messages(team_id, channel_id, since=since)
        added = vs.add_messages(messages, team_name, channel_name, project_id=project_id)
        vs.update_sync_time(team_id, channel_id, project_id=project_id)
        replies_count = sum(1 for m in messages if m.get("message_type") == "reply")
        posts_count = len(messages) - replies_count
        return added, len(messages), posts_count, replies_count
    except Exception as e:
        raise e


def sync_group_chat(chat_id: str, chat_name: str):
    client = get_teams_client_for_project()
    if not client:
        raise Exception("Teams client unavailable. Check your credentials in the Data Sources tab.")
    vs = st.session_state.vector_store
    project_id = get_current_project_id()

    sync_key = f"chat-{chat_id}"
    last_sync_str = vs.get_last_sync(sync_key, "group_chat", project_id=project_id)
    since = None
    if last_sync_str != "Never":
        try:
            since = datetime.fromisoformat(last_sync_str)
        except (ValueError, TypeError):
            since = None

    try:
        messages = client.get_chat_messages(chat_id, since=since)
        added = vs.add_messages(messages, chat_name, "Group Chat", project_id=project_id)
        vs.update_sync_time(sync_key, "group_chat", project_id=project_id)
        return added, len(messages)
    except Exception as e:
        raise e


def render_project_manager():
    st.header("Project Manager")
    vs = st.session_state.vector_store

    projects = vs.get_projects()

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Your Projects")
    with col2:
        with st.popover("Create New Project"):
            new_name = st.text_input("Project Name", key="new_project_name")
            new_desc = st.text_input("Description (optional)", key="new_project_desc")
            if st.button("Create", type="primary"):
                if new_name:
                    try:
                        project = vs.create_project(new_name, new_desc)
                        st.session_state.current_project = project
                        st.success(f"Project '{new_name}' created!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create project: {e}")
                else:
                    st.warning("Please enter a project name.")

    if not projects:
        st.info("No projects yet. Create one to get started!")
        return

    for proj in projects:
        proj_stats = vs.get_stats(project_id=proj["id"])
        sources = vs.get_data_sources(proj["id"])
        is_selected = st.session_state.current_project and st.session_state.current_project["id"] == proj["id"]

        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                label = f"**{proj['name']}**"
                if is_selected:
                    label += " (Active)"
                st.markdown(label)
                if proj["description"]:
                    st.caption(proj["description"])
            with col2:
                st.caption(f"{proj_stats['total_messages']} messages | {len(sources)} data source(s)")
            with col3:
                if not is_selected:
                    if st.button("Select", key=f"sel_{proj['id']}"):
                        st.session_state.current_project = proj
                        st.session_state.groups_list = []
                        st.session_state.users_list = []
                        st.session_state.chat_history = []
                        st.session_state.channels_map = {}
                        st.rerun()
                if st.button("Delete", key=f"del_{proj['id']}"):
                    vs.delete_project(proj["id"])
                    if is_selected:
                        st.session_state.current_project = None
                    cache_key = f"teams_client_{proj['id']}"
                    if cache_key in st.session_state:
                        del st.session_state[cache_key]
                    st.rerun()


def render_data_sources():
    st.header("Data Sources")

    project = st.session_state.current_project
    if not project:
        st.warning("Please select a project first from the Project Manager tab.")
        return

    vs = st.session_state.vector_store
    sources = vs.get_data_sources(project["id"])

    st.write(f"Data sources for **{project['name']}**:")

    if sources:
        for src in sources:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    source_label = src["source_type"].replace("_", " ").title()
                    config = src.get("config", {})
                    connected = all([config.get("client_id"), config.get("client_secret"), config.get("tenant_id")])
                    status = "Connected" if connected else "Not configured"
                    st.markdown(f"**{source_label}** — {status}")
                    if config.get("tenant_id"):
                        st.caption(f"Tenant: {config['tenant_id'][:8]}...")
                with col2:
                    if st.button("Remove", key=f"rm_src_{src['id']}"):
                        vs.remove_data_source(src["id"], project["id"])
                        for k in [f"teams_client_{project['id']}", f"teams_list_{project['id']}", f"users_list_{project['id']}"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        st.session_state.channels_map = {}
                        st.session_state.groups_list = []
                        st.rerun()

    st.divider()
    st.subheader("Add Data Source")

    source_types = ["Microsoft Teams"]
    selected_type = st.selectbox("Source Type", source_types)

    if selected_type == "Microsoft Teams":
        has_teams_source = any(s["source_type"] == "microsoft_teams" for s in sources)
        if has_teams_source:
            st.info("Microsoft Teams source already added to this project. Remove it first to add a new one.")

            teams_source = next(s for s in sources if s["source_type"] == "microsoft_teams")
            config = teams_source.get("config", {})
            is_configured = all([config.get("client_id"), config.get("client_secret"), config.get("tenant_id")])

            if not is_configured:
                st.warning("This data source needs Azure AD credentials to connect.")

            with st.expander("Update Credentials" if is_configured else "Configure Credentials", expanded=not is_configured):
                _render_teams_credential_form(teams_source["id"], project["id"], config)
        else:
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
   - `Chat.Read.All`
   - `User.Read.All`
4. Click "Grant admin consent"

**Step 3: Create a Client Secret**
1. Go to "Certificates & secrets"
2. Click "New client secret"
3. Copy the secret value (you won't see it again)

**Step 4: Get your IDs**
- **Client ID**: Found on the app's Overview page (Application ID)
- **Tenant ID**: Found on the app's Overview page (Directory ID)
                """)

            st.subheader("Enter Azure AD Credentials")
            tenant_id = st.text_input("Tenant ID", key="new_ds_tenant_id", type="password")
            client_id = st.text_input("Client ID", key="new_ds_client_id", type="password")
            client_secret = st.text_input("Client Secret", key="new_ds_client_secret", type="password")

            if st.button("Add Microsoft Teams", type="primary"):
                if not all([tenant_id, client_id, client_secret]):
                    st.error("Please fill in all three credential fields.")
                else:
                    with st.spinner("Verifying connection..."):
                        try:
                            test_client = TeamsClient(client_id, client_secret, tenant_id)
                            test_client.get_teams()
                            vs.add_data_source(
                                project["id"],
                                "microsoft_teams",
                                {
                                    "client_id": client_id,
                                    "client_secret": client_secret,
                                    "tenant_id": tenant_id,
                                },
                            )
                            st.success("Microsoft Teams data source added and verified!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Connection failed: {str(e)}. Please check your credentials.")


def _render_teams_credential_form(source_id: str, project_id: str, current_config: dict):
    vs = st.session_state.vector_store

    tenant_id = st.text_input(
        "Tenant ID",
        value=current_config.get("tenant_id", ""),
        key=f"upd_tenant_{source_id}",
        type="password",
    )
    client_id = st.text_input(
        "Client ID",
        value=current_config.get("client_id", ""),
        key=f"upd_client_{source_id}",
        type="password",
    )
    client_secret = st.text_input(
        "Client Secret",
        value=current_config.get("client_secret", ""),
        key=f"upd_secret_{source_id}",
        type="password",
    )

    if st.button("Save & Verify", key=f"save_creds_{source_id}"):
        if not all([tenant_id, client_id, client_secret]):
            st.error("Please fill in all three credential fields.")
        else:
            with st.spinner("Verifying connection..."):
                try:
                    test_client = TeamsClient(client_id, client_secret, tenant_id)
                    test_client.get_teams()
                    vs.update_data_source_config(
                        source_id,
                        {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "tenant_id": tenant_id,
                        },
                    )
                    for k in [f"teams_client_{project_id}", f"teams_list_{project_id}", f"users_list_{project_id}"]:
                        if k in st.session_state:
                            del st.session_state[k]
                    st.session_state.channels_map = {}
                    st.session_state.groups_list = []
                    st.success("Credentials updated and verified!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Connection failed: {str(e)}")


def render_channel_selector():
    st.header("Sync Teams Channels")

    project = st.session_state.current_project
    if not project:
        st.warning("Please select a project first from the Project Manager tab.")
        return

    if not is_project_connected():
        st.info("Configure Microsoft Teams credentials in the Data Sources tab first.")
        return

    client = get_teams_client_for_project()
    if not client:
        st.error("Failed to connect to Microsoft Teams. Check your credentials in the Data Sources tab.")
        return

    project_id = project["id"]
    vs = st.session_state.vector_store

    teams_cache_key = f"teams_list_{project_id}"
    if teams_cache_key not in st.session_state:
        try:
            st.session_state[teams_cache_key] = client.get_teams()
        except Exception as e:
            st.error(f"Failed to load teams: {str(e)}")
            return

    teams = st.session_state[teams_cache_key]
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
                last_sync = vs.get_last_sync(team_id, ch["id"], project_id=project_id)
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


def render_group_chat_selector():
    st.header("Sync Group Chats")

    project = st.session_state.current_project
    if not project:
        st.warning("Please select a project first from the Project Manager tab.")
        return

    if not is_project_connected():
        st.info("Configure Microsoft Teams credentials in the Data Sources tab first.")
        return

    client = get_teams_client_for_project()
    if not client:
        st.error("Failed to connect to Microsoft Teams. Check your credentials in the Data Sources tab.")
        return

    users_cache_key = f"users_list_{project['id']}"
    if users_cache_key not in st.session_state:
        with st.spinner("Loading users..."):
            try:
                users = client.get_users()
                st.session_state[users_cache_key] = users
            except Exception as e:
                st.error(f"Failed to load users: {str(e)}")
                return

    users = st.session_state[users_cache_key]
    if not users:
        st.info("No users found. Make sure the app has User.Read.All permission.")
        return

    vs = st.session_state.vector_store
    user_options = {f"{u['name']} ({u['email']})" if u['email'] else u['name']: u['id'] for u in users}
    selected_user_labels = st.multiselect(
        "Select users to load group chats from",
        options=list(user_options.keys()),
    )

    if selected_user_labels:
        selected_user_ids = [user_options[label] for label in selected_user_labels]

        if st.button("Load Group Chats"):
            with st.spinner(f"Loading group chats for {len(selected_user_ids)} user(s)..."):
                try:
                    chats = client.get_group_chats(user_ids=selected_user_ids)
                    st.session_state.groups_list = chats
                except Exception as e:
                    st.error(f"Failed to load group chats: {str(e)}")
                    return

    chats = st.session_state.groups_list
    if not chats:
        if selected_user_labels:
            st.info("No group chats found for the selected users. Click 'Load Group Chats' to search.")
        else:
            st.info("Select one or more users above, then click 'Load Group Chats'.")
        return

    st.write(f"Found {len(chats)} group chat(s).")

    selected_chats = []
    for chat in chats:
        sync_key = f"chat-{chat['id']}"
        last_sync = vs.get_last_sync(sync_key, "group_chat", project_id=project["id"])
        label = chat["name"]
        members_str = f"{chat['member_count']} members"

        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            if st.checkbox(label, key=f"gc_{chat['id']}"):
                selected_chats.append(chat)
            st.caption(members_str)
        with col2:
            st.caption(f"Last sync: {last_sync}")
        with col3:
            if st.button("Sync", key=f"sync_gc_{chat['id']}"):
                with st.spinner(f"Syncing {chat['name']}..."):
                    try:
                        added, total = sync_group_chat(chat["id"], chat["name"])
                        st.success(
                            f"Synced: {added} new messages added "
                            f"({total} fetched)"
                        )
                    except Exception as e:
                        st.error(f"Sync failed: {str(e)}")

    if selected_chats:
        if st.button("Sync All Selected Group Chats", type="primary"):
            progress = st.progress(0)
            total_added = 0
            for i, chat in enumerate(selected_chats):
                with st.spinner(f"Syncing {chat['name']}..."):
                    try:
                        added, _ = sync_group_chat(chat["id"], chat["name"])
                        total_added += added
                    except Exception as e:
                        st.error(f"Failed: {chat['name']}: {str(e)}")
                progress.progress((i + 1) / len(selected_chats))
            st.success(f"Sync complete! Added {total_added} new messages total.")


def render_knowledge_base():
    st.header("Knowledge Base")

    project = st.session_state.current_project
    if not project:
        st.warning("Please select a project first from the Project Manager tab.")
        return

    vs = st.session_state.vector_store
    project_id = project["id"]
    stats = vs.get_stats(project_id=project_id)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Messages", stats["total_messages"])
    with col2:
        st.metric("Teams/Sources Indexed", len(stats["teams"]))
    with col3:
        st.metric("Channels Indexed", len(stats["channels"]))

    if stats["total_messages"] == 0:
        st.info("No messages indexed yet. Go to the Channels or Group Chats tab and sync some data first.")
        return

    st.subheader("Quick Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Generate Summary"):
            with st.spinner("Generating summary..."):
                results = vs.search("project status updates decisions", n_results=30, project_id=project_id)
                if results:
                    summary = summarize_channel(results)
                    st.markdown(summary)
                else:
                    st.warning("No messages found to summarize.")
    with col2:
        if st.button("Clear Project Data"):
            vs.clear_project(project_id)
            st.success("Project data cleared.")
            st.rerun()


def render_chat():
    st.header("Ask About Your Project")

    project = st.session_state.current_project
    if not project:
        st.warning("Please select a project first from the Project Manager tab.")
        return

    vs = st.session_state.vector_store
    project_id = project["id"]
    stats = vs.get_stats(project_id=project_id)

    if stats["total_messages"] == 0:
        st.info("No messages indexed yet. Sync some data first to start asking questions.")
        return

    st.write(f"Ask questions about **{project['name']}** — based on indexed conversations and data sources.")

    filter_team = None
    filter_channel = None
    with st.expander("Filters (optional)"):
        if stats["teams"]:
            filter_team = st.selectbox(
                "Filter by Source/Team",
                options=["All"] + stats["teams"],
            )
            if filter_team == "All":
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

    if prompt := st.chat_input("Ask a question about your project..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching and generating answer..."):
                filters = {}
                if filter_team:
                    filters["team"] = filter_team
                if filter_channel:
                    filters["channel"] = filter_channel

                context_results = vs.search(
                    prompt,
                    n_results=20,
                    filters=filters if filters else None,
                    project_id=project_id,
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

    st.title("Teams Knowledge Base")
    st.caption("Extract, index, and query your Microsoft Teams conversations with AI")

    tab_projects, tab_sources, tab_channels, tab_chats, tab_kb, tab_ask = st.tabs([
        "Projects",
        "Data Sources",
        "Channels",
        "Group Chats",
        "Knowledge Base",
        "Ask Questions",
    ])

    with tab_projects:
        render_project_manager()
    with tab_sources:
        render_data_sources()
    with tab_channels:
        render_channel_selector()
    with tab_chats:
        render_group_chat_selector()
    with tab_kb:
        render_knowledge_base()
    with tab_ask:
        render_chat()

    with st.sidebar:
        st.subheader("Current Project")
        if st.session_state.current_project:
            proj = st.session_state.current_project
            st.success(f"**{proj['name']}**")

            vs = st.session_state.vector_store
            stats = vs.get_stats(project_id=proj["id"])

            connected = is_project_connected()
            if connected:
                st.caption("Teams: Connected")
            else:
                st.caption("Teams: Not configured")

            st.metric("Messages Indexed", stats["total_messages"])

            if stats["teams"]:
                st.write("**Sources:**")
                for t in stats["teams"]:
                    st.write(f"  - {t}")

            if stats["channels"]:
                st.write("**Channels:**")
                for c in stats["channels"]:
                    st.write(f"  - {c}")
        else:
            st.warning("No project selected")

        st.divider()
        st.caption("Powered by Microsoft Graph API & OpenAI")


if __name__ == "__main__":
    main()
