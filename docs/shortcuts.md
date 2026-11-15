# Siri and the share sheet

Two Apple Shortcuts connect your iPhone to the app. Both use the addresses and
the private key shown in the app under **Settings → Siri and the share sheet**.
Anyone with the key can add to your list, so don't share the Shortcuts with the
key inside.

These steps were written from the API, not yet tried on a phone; the action
names may differ slightly between iOS versions.

## "Add to groceries" (Siri)

In the Shortcuts app, create a shortcut named **Add to groceries** with these actions:

1. **Ask for Input** – type *Text*, prompt "What should I add?"
2. **Get Contents of URL**
   - URL: the *Add to groceries* address from Settings
   - Method: **POST**
   - Headers: `Authorization` = `Bearer YOUR_KEY`
   - Request Body: **JSON**, with one field `item` (Text) set to *Provided Input*
3. **Get Dictionary Value** – get the value for `message` from *Contents of URL*
4. **Speak Text** (or **Show Result**) – *Dictionary Value*

Say **"Hey Siri, add to groceries"**, then the item. You can say several:
"milk, eggs and bread". Siri answers "Added milk, eggs, bread to your
groceries", or tells you it is already on the list.

## "Save recipe" (share sheet)

One shortcut handles screenshots, saved videos and links. Create a shortcut named
**Save recipe**:

1. In the shortcut's details, turn on **Show in Share Sheet** and accept **Images**,
   **Media** and **URLs**.
2. **If** *Shortcut Input* **has any value** of type... use three branches with
   **Get Type**, or create three small shortcuts instead if that is easier:
   - **Screenshots** (one or several): **Get Contents of URL** to the
     *Save a recipe screenshot* address, Method **POST**, header
     `Authorization` = `Bearer YOUR_KEY`, Request Body **Form**, with a field
     `files` of type *File* set to *Shortcut Input*. Several selected screenshots
     are sent together and read as one recipe, in the order you picked them.
   - **A saved video**: the same, but to the address ending in
     `/api/shortcuts/recipe-video`, with a field `file` set to *Shortcut Input*.
   - **A link** (TikTok's **Share → Copy link**, or Safari): the same, but to the
     address ending in `/api/shortcuts/recipe-link`, with Request Body **JSON** and
     a field `url` (Text) set to *Shortcut Input*.
3. **Get Dictionary Value** – `message`
4. **Show Notification** – *Dictionary Value*

The recipe appears in the app marked "check this" so you can confirm the amounts.

### Which one to use for TikTok

- **Link**: fastest. It reads the video's caption through TikTok's official embed
  service. Works when the caption lists the ingredients.
- **Video**: in TikTok, **Share → Save video**, then share it from Photos. The AI
  watches the video and listens to it, so it also finds recipes that are only
  spoken or shown on screen. Takes up to a minute.

Limits: up to 10 images for one recipe, 20 MB in total; videos up to 20 MB
(a typical 1-minute TikTok is well under that).
