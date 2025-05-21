import streamlit as st

def page1():
    st.title("Anthopic Web Search")

def page2():
    st.title('Perplexity AI Web')

pg = st.navigation([
    st.Page("streamlit_app.py", title="Anthropic web search", icon="🔥"),
    st.Page("streamlit_app_2.py", title="Perplexity AI", icon="📄"),
])
pg.run()