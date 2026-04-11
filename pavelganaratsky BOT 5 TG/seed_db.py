import asyncio
import datetime
from database import init_db, add_message

schedule = [
    ("29.6", "02.03", "14:07"),
    ("14.6", "09.03", "16:58"),
    ("10.2", "12.03", "05:29"),
    ("3.4", "21.03", "08:13"),
    ("2.2", "22.03", "09:06"),
    ("29.6", "29.03", "21:04"),
]

async def seed():
    await init_db()
    current_year = datetime.datetime.now().year
    
    for text, date_str, time_str in schedule:
        dt_str = f"{current_year}.{date_str} {time_str}"
        dt = datetime.datetime.strptime(dt_str, "%Y.%d.%m %H:%M")
        await add_message(text, dt)
        print(f"Added: {text} at {dt}")

if __name__ == "__main__":
    if asyncio.get_event_loop_policy().__class__.__name__ == 'WindowsProactorEventLoopPolicy':
         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
