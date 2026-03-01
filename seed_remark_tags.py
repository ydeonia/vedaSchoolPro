"""Seed Remark Tags — Pre-defined teacher feedback tags per subject.
Run: python seed_remark_tags.py
These tags let teachers give rich feedback in 30 seconds by tapping, not typing."""

import asyncio, uuid
from database import engine, async_session, Base
from models.mega_modules import RemarkTag, RemarkCategory

# ═══════════════════════════════════════════════════════════
# REMARK TAGS — Organized by Subject + Category
# Format: (subject, tag_text, category, icon)
# ═══════════════════════════════════════════════════════════

TAGS = [
    # ──────── MATHEMATICS ────────
    ("Mathematics", "Excellent problem-solving skills", "strength", "🌟"),
    ("Mathematics", "Strong in mental calculations", "strength", "🧠"),
    ("Mathematics", "Good at geometry & shapes", "strength", "📐"),
    ("Mathematics", "Quick learner in new concepts", "strength", "⚡"),
    ("Mathematics", "Shows logical thinking", "strength", "🎯"),
    ("Mathematics", "Weak in Algebra", "concern", "⚠️"),
    ("Mathematics", "Struggles with Fractions & Decimals", "concern", "⚠️"),
    ("Mathematics", "Needs help with Word Problems", "concern", "⚠️"),
    ("Mathematics", "Calculation errors — careless mistakes", "concern", "⚠️"),
    ("Mathematics", "Weak in Geometry proofs", "concern", "⚠️"),
    ("Mathematics", "Trigonometry needs more practice", "concern", "⚠️"),
    ("Mathematics", "Struggles with graphs & data interpretation", "concern", "⚠️"),
    ("Mathematics", "Does not show steps in solutions", "concern", "⚠️"),
    ("Mathematics", "Practice Chapter exercises daily — 30 min", "suggestion", "💡"),
    ("Mathematics", "Use NCERT solved examples for revision", "suggestion", "💡"),
    ("Mathematics", "Focus on formula memorization", "suggestion", "💡"),
    ("Mathematics", "Try solving previous year papers", "suggestion", "💡"),
    ("Mathematics", "Work on speed — timed practice recommended", "suggestion", "💡"),

    # ──────── ENGLISH ────────
    ("English", "Excellent vocabulary and expression", "strength", "🌟"),
    ("English", "Strong reading comprehension", "strength", "📖"),
    ("English", "Creative writing skills are impressive", "strength", "✍️"),
    ("English", "Good at grammar and sentence structure", "strength", "🎯"),
    ("English", "Confident in speaking and presentation", "strength", "🗣️"),
    ("English", "Spelling errors are frequent", "concern", "⚠️"),
    ("English", "Grammar needs significant improvement", "concern", "⚠️"),
    ("English", "Handwriting is not legible", "concern", "⚠️"),
    ("English", "Weak in essay and letter writing", "concern", "⚠️"),
    ("English", "Poor vocabulary — limited word usage", "concern", "⚠️"),
    ("English", "Reading speed is below expected level", "concern", "⚠️"),
    ("English", "Struggles with comprehension passages", "concern", "⚠️"),
    ("English", "Tenses and verb forms are often wrong", "concern", "⚠️"),
    ("English", "Does not attempt creative writing sections", "concern", "⚠️"),
    ("English", "Punctuation and capitalization errors", "concern", "⚠️"),
    ("English", "Read English newspaper 15 min daily", "suggestion", "💡"),
    ("English", "Maintain a personal dictionary for new words", "suggestion", "💡"),
    ("English", "Practice cursive handwriting daily", "suggestion", "💡"),
    ("English", "Write one paragraph daily on any topic", "suggestion", "💡"),
    ("English", "Read storybooks — Ruskin Bond, R.K. Narayan", "suggestion", "💡"),
    ("English", "Focus on NCERT grammar exercises", "suggestion", "💡"),

    # ──────── HINDI ────────
    ("Hindi", "Excellent in Hindi literature and poetry", "strength", "🌟"),
    ("Hindi", "Strong grasp of Hindi grammar (vyakaran)", "strength", "📝"),
    ("Hindi", "Beautiful handwriting in Devnagari", "strength", "✍️"),
    ("Hindi", "Good at Hindi creative writing (rachnatmak)", "strength", "🎯"),
    ("Hindi", "Matras and spelling errors in Hindi", "concern", "⚠️"),
    ("Hindi", "Hindi handwriting needs improvement", "concern", "⚠️"),
    ("Hindi", "Weak in Hindi comprehension (apathit gadyansh)", "concern", "⚠️"),
    ("Hindi", "Letter/application writing needs work", "concern", "⚠️"),
    ("Hindi", "Sandhi and Samas concepts are unclear", "concern", "⚠️"),
    ("Hindi", "Does not read Hindi textbook at home", "concern", "⚠️"),
    ("Hindi", "Read Hindi newspaper or magazine weekly", "suggestion", "💡"),
    ("Hindi", "Practice Devnagari writing 15 min daily", "suggestion", "💡"),
    ("Hindi", "Revise vyakaran chapters from NCERT", "suggestion", "💡"),
    ("Hindi", "Learn one new muhavara/lokokti weekly", "suggestion", "💡"),

    # ──────── SCIENCE ────────
    ("Science", "Excellent understanding of concepts", "strength", "🌟"),
    ("Science", "Very good in practical/lab work", "strength", "🔬"),
    ("Science", "Strong in Biology — diagrams are neat", "strength", "🧬"),
    ("Science", "Physics problem-solving is excellent", "strength", "⚡"),
    ("Science", "Chemistry equations are well-balanced", "strength", "🧪"),
    ("Science", "Shows curiosity — asks good questions", "strength", "🤔"),
    ("Science", "Weak in Physics numerical problems", "concern", "⚠️"),
    ("Science", "Chemical equations and balancing unclear", "concern", "⚠️"),
    ("Science", "Biology diagrams are not labelled properly", "concern", "⚠️"),
    ("Science", "Does not understand experiment procedures", "concern", "⚠️"),
    ("Science", "Struggles with scientific terminology", "concern", "⚠️"),
    ("Science", "Weak in unit conversions", "concern", "⚠️"),
    ("Science", "Does not revise previous chapters", "concern", "⚠️"),
    ("Science", "Practice NCERT intext questions thoroughly", "suggestion", "💡"),
    ("Science", "Draw and label diagrams while revising", "suggestion", "💡"),
    ("Science", "Watch NCERT video explanations for difficult topics", "suggestion", "💡"),
    ("Science", "Maintain a formula sheet for Physics & Chemistry", "suggestion", "💡"),
    ("Science", "Solve exemplar problems for deeper understanding", "suggestion", "💡"),

    # ──────── SOCIAL STUDIES / SOCIAL SCIENCE ────────
    ("Social Studies", "Excellent in History — dates and events", "strength", "🌟"),
    ("Social Studies", "Good understanding of Geography concepts", "strength", "🌍"),
    ("Social Studies", "Strong in Civics — understands governance well", "strength", "🏛️"),
    ("Social Studies", "Map work is accurate and neat", "strength", "🗺️"),
    ("Social Studies", "Weak in remembering historical dates", "concern", "⚠️"),
    ("Social Studies", "Geography map skills need improvement", "concern", "⚠️"),
    ("Social Studies", "Civics concepts are not clear", "concern", "⚠️"),
    ("Social Studies", "Does not write descriptive answers properly", "concern", "⚠️"),
    ("Social Studies", "Economics section needs more attention", "concern", "⚠️"),
    ("Social Studies", "Answers are too short — lacks detail", "concern", "⚠️"),
    ("Social Studies", "Create timeline charts for History chapters", "suggestion", "💡"),
    ("Social Studies", "Practice map pointing weekly", "suggestion", "💡"),
    ("Social Studies", "Write 5-point answers for practice", "suggestion", "💡"),
    ("Social Studies", "Read NCERT chapter summaries before exams", "suggestion", "💡"),

    # ──────── GENERAL / BEHAVIORAL ────────
    ("General", "Excellent discipline and behavior", "strength", "🌟"),
    ("General", "Very attentive in class", "strength", "👀"),
    ("General", "Helps classmates — good team player", "strength", "🤝"),
    ("General", "Shows leadership qualities", "strength", "👑"),
    ("General", "Always completes homework on time", "strength", "✅"),
    ("General", "Active in extra-curricular activities", "strength", "🎭"),
    ("General", "Respectful to teachers and staff", "strength", "🙏"),
    ("General", "Participates enthusiastically in class", "strength", "🙋"),
    ("General", "Comes prepared for class daily", "strength", "📚"),
    ("General", "Often distracted in class", "concern", "⚠️"),
    ("General", "Homework frequently incomplete or missing", "concern", "⚠️"),
    ("General", "Handwriting across subjects needs improvement", "concern", "⚠️"),
    ("General", "Does not bring required books/stationery", "concern", "⚠️"),
    ("General", "Irregular attendance — affects learning", "concern", "⚠️"),
    ("General", "Talks excessively during class", "concern", "⚠️"),
    ("General", "Time management during exams is poor", "concern", "⚠️"),
    ("General", "Does not attempt all questions in exam", "concern", "⚠️"),
    ("General", "Needs to be more organized with notes", "concern", "⚠️"),
    ("General", "Screen time may be affecting studies", "concern", "⚠️"),
    ("General", "Set a daily study timetable at home", "suggestion", "💡"),
    ("General", "Reduce screen time — focus on reading", "suggestion", "💡"),
    ("General", "Revise previous day's topics for 20 min", "suggestion", "💡"),
    ("General", "Parent-teacher meeting recommended", "suggestion", "💡"),
    ("General", "Consider extra coaching for weak subjects", "suggestion", "💡"),
    ("General", "Encourage child to read books daily", "suggestion", "💡"),
    ("General", "Ensure 8 hours sleep for better concentration", "suggestion", "💡"),
    ("General", "Praise and motivate — child responds well to encouragement", "suggestion", "💡"),
    ("General", "Child has potential — needs consistent effort", "suggestion", "💡"),

    # ──────── COMPUTER SCIENCE ────────
    ("Computer Science", "Good at programming concepts", "strength", "🌟"),
    ("Computer Science", "Typing speed is excellent", "strength", "⌨️"),
    ("Computer Science", "Weak in coding logic — needs practice", "concern", "⚠️"),
    ("Computer Science", "Does not practice on computer at home", "concern", "⚠️"),
    ("Computer Science", "Practice coding exercises on paper first", "suggestion", "💡"),

    # ──────── PHYSICAL EDUCATION ────────
    ("Physical Education", "Excellent in sports and athletics", "strength", "🏅"),
    ("Physical Education", "Good team spirit and sportsmanship", "strength", "🤝"),
    ("Physical Education", "Needs to improve physical fitness", "concern", "⚠️"),
    ("Physical Education", "Does not participate in PT exercises", "concern", "⚠️"),
    ("Physical Education", "Encourage outdoor play for 1 hour daily", "suggestion", "💡"),

    # ──────── ART & CRAFT ────────
    ("Art & Craft", "Excellent creativity and artistic skills", "strength", "🎨"),
    ("Art & Craft", "Neat and detailed artwork", "strength", "✨"),
    ("Art & Craft", "Needs to put more effort in art projects", "concern", "⚠️"),
    ("Art & Craft", "Encourage drawing and coloring at home", "suggestion", "💡"),

    # ──────── MUSIC ────────
    ("Music", "Good sense of rhythm and melody", "strength", "🎵"),
    ("Music", "Sings with confidence", "strength", "🎤"),
    ("Music", "Shy in music class — needs encouragement", "concern", "⚠️"),
    ("Music", "Listen to classical/devotional music at home", "suggestion", "💡"),
]


async def seed_remark_tags():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as db:
        # Check if tags already exist
        from sqlalchemy import select, func
        count = (await db.execute(select(func.count(RemarkTag.id)))).scalar()
        if count > 0:
            print(f"⚠️  {count} remark tags already exist. Skipping seed.")
            return
        
        for i, (subject, text, cat, icon) in enumerate(TAGS):
            tag = RemarkTag(
                branch_id=None,  # Global defaults (available to all schools)
                subject_name=subject,
                tag_text=text,
                category=RemarkCategory(cat),
                icon=icon,
                sort_order=i,
                is_active=True,
            )
            db.add(tag)
        
        await db.commit()
        print(f"✅ Seeded {len(TAGS)} remark tags across {len(set(t[0] for t in TAGS))} subjects")
        
        # Print summary
        from collections import Counter
        subject_counts = Counter(t[0] for t in TAGS)
        category_counts = Counter(t[2] for t in TAGS)
        print(f"\n📊 By Subject:")
        for subj, cnt in subject_counts.most_common():
            print(f"   {subj}: {cnt} tags")
        print(f"\n📊 By Category:")
        for cat, cnt in category_counts.most_common():
            print(f"   {cat}: {cnt} tags")


if __name__ == "__main__":
    asyncio.run(seed_remark_tags())
