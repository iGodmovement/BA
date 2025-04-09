from flask import Flask, render_template, request, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from PIL import Image
import os
import uuid
import webbrowser
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import pdfkit

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SECRET_KEY'] = os.urandom(24)  # Sicherer Zufallsschlüssel
db = SQLAlchemy(app)

# Bildzuordnung
IMAGE_TERMS = {
    '1': 'Plattenbau',
    '2': 'Industire oder Sporthallen',
    '3': 'Mehrfamilienhaus',
    '4': 'Einfamilienhaus'
}

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(20), nullable=False)
    text = db.Column(db.String(200), nullable=False)
    subtitle = db.Column(db.String(200), nullable=True)
    answers = db.relationship('Answer', backref='question', lazy=True)
    image = db.Column(db.String(200), nullable=True)
    info_popup = db.Column(db.String(500), nullable=True)  # Popup-Text


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.String(200), nullable=True)
    score = db.Column(db.Integer, nullable=True)
    info_popup = db.Column(db.String(500), nullable=True)

def get_questions(module):
    questions = Question.query.filter_by(module=module).all()
    if not questions:
        abort(404, description="Keine Fragen für dieses Modul gefunden")
    return questions

def calculate_module_score(answers, module):
    if module == 'Basic':
        return 0  # Basic-Modul gibt immer 0 Punkte
    if not answers:  # Falls answers leer/undefined
        return 0
    module_score = 0
    for question_id, answer in answers.items():
        if isinstance(answer, dict) and answer.get('score') is not None:
            module_score += answer['score']
    return module_score


def resize_image(image_path, size=(300, 300)):
    with Image.open(image_path) as img:
        img.thumbnail(size, Image.LANCZOS)
        img.save(image_path, quality=95, optimize=True)

@app.route('/')
def index():
    return redirect(url_for('info'))

@app.route('/info', methods=['GET', 'POST'])
def info():
    session.clear()
    if request.method == 'POST':
        return redirect(url_for('basic_quiz'))
    return render_template('info.html')

@app.route('/basic_quiz/', methods=['GET', 'POST'])
def basic_quiz():
    module = 'Basic'
    questions = get_questions(module)
    total_questions = len(questions)

    # Session-Initialisierung
    session.setdefault('question_index', 0)
    session.setdefault('answers', {})

    if session.get('module') != module:
        session['module'] = module
        session['question_index'] = 0
        session['answers'] = {}

    question_index = session['question_index']

    if request.method == 'POST':
        # "Zurück"-Button wurde geklickt
        if 'back' in request.form:
            if question_index > 0:
                session['question_index'] -= 1
            return redirect(url_for('basic_quiz'))

        # "Weiter"-Button wurde geklickt
        if 'next' in request.form:
            question = questions[question_index]
            answer_id = request.form.get('answer')
            free_text = request.form.get('free_text')

            if answer_id:
                answer = Answer.query.get(answer_id)
                session['answers'][str(question.id)] = {
                    'text': answer.text,
                    'score': answer.score
                }
            elif free_text:
                session['answers'][str(question.id)] = {
                    'text': free_text,
                    'score': None
                }

            session['question_index'] += 1

            # Weiterleitung zur Zusammenfassung nach der letzten Frage
            if session['question_index'] >= total_questions:
                session['basic_answers'] = session['answers']
                return redirect(url_for('choose_module'))

        return redirect(url_for('basic_quiz'))

    # GET-Request Handling
    try:
        question = questions[question_index]
    except IndexError:
        return redirect(url_for('choose_module'))

    return render_template(
        'basic_quiz.html',
        module=module,
        question=question,
        question_index=question_index,
        total_questions=total_questions,
        answers=session['answers']
    )

@app.route('/choose_module/', methods=['GET', 'POST'])
def choose_module():
    if request.method == 'POST':
        selected_module = request.form.get('module')
        # Session für neues Modul zurücksetzen
        session.pop('answers', None)
        session.pop('question_index', None)
        session['module'] = selected_module
        return redirect(url_for('quiz', module=selected_module))
    return render_template('choose_module.html')

@app.route('/quiz/<module>', methods=['GET', 'POST'])
def quiz(module):
    questions = get_questions(module)
    total_questions = len(questions)

    # Session-Initialisierung
    session.setdefault('question_index', 0)
    session.setdefault('answers', {})

    if session.get('module') != module:
        session['module'] = module
        session['question_index'] = 0
        session['answers'] = {}

    question_index = session['question_index']

    if request.method == 'POST':
        # "Zurück"-Button Logik
        if 'back' in request.form:
            if question_index > 0:
                session['question_index'] -= 1
            return redirect(url_for('quiz', module=module))

        # "Weiter"-Button Logik
        if 'next' in request.form:
            question = questions[question_index]
            answer_id = request.form.get('answer')
            free_text = request.form.get('free_text')

            if answer_id:
                answer = Answer.query.get(answer_id)
                session['answers'][str(question.id)] = {
                    'text': answer.text,
                    'score': answer.score
                }
            elif free_text:
                session['answers'][str(question.id)] = {
                    'text': free_text,
                    'score': None
                }

            session['question_index'] += 1

            # Weiterleitung zur Zusammenfassung nach der letzten Frage
            if session['question_index'] >= total_questions:
                session[f'{module.lower()}_answers'] = session['answers']
                return redirect(url_for('summary'))

        return redirect(url_for('quiz', module=module))

    # GET-Request Handling
    try:
        question = questions[question_index]
    except IndexError:
        return redirect(url_for('summary'))

    return render_template(
        f'{module.lower()}_quiz.html',
        question=question,
        question_index=question_index,
        total_questions=total_questions,
        answers=session['answers']
    )


@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' in request.files:
        image = request.files['image']
        if image.filename != '':
            image_path = os.path.join(app.config['static/images'], image.filename)
            image.save(image_path)
            resize_image(image_path)
            return 'Image uploaded and resized successfully'
    return 'No image uploaded', 400

@app.route('/summary/')
def summary():
    basic_answers = session.get('basic_answers', {})
    express_answers = session.get('express_answers', {})
    advanced_answers = session.get('advanced_answers', {})  # Key: 'Advanced'

    # Korrekte Schlüsselverwendung
    module_scores = {
        'Basic': calculate_module_score(basic_answers, 'Basic'),
        'Express': calculate_module_score(express_answers, 'Express'),
        'Advanced': calculate_module_score(advanced_answers, 'Advanced')  # Key angepasst
    }

    total_score = module_scores['Express'] + module_scores['Advanced']

    # Schlüssel konsistent halten
    session['all_answers'] = {
        'Basic': basic_answers,
        'Express': express_answers,
        'Advanced': advanced_answers  # Key: 'Advanced'
    }
    session['module_scores'] = module_scores  # Wichtig für die PDF
    questions = {str(q.id): q for q in Question.query.all()}

    return render_template(
        'summary.html',
        all_answers=session['all_answers'],
        module_scores=module_scores,
        total_score=total_score,
        questions=questions
    )


@app.route('/download_pdf', methods=['GET'])
def download_pdf():
    # Daten aus der Session abrufen
    all_answers = session.get('all_answers', {})
    module_scores = session.get('module_scores', {})
    questions = {str(q.id): q for q in Question.query.all()}  # Fragen aus der Datenbank

    # PDF-Konfiguration
    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Titel hinzufügen
    elements.append(Paragraph("Sanierungsbewertung - Zusammenfassung", styles['Title']))
    elements.append(Spacer(1, 20))

    # Module verarbeiten
    for module in ['Basic', 'Express', 'Advanced']:
        if module in all_answers and all_answers[module]:
            # Modul-Titel
            elements.append(Paragraph(f"{module} Modul", styles['Heading2']))

            # Modul-Score hervorheben (außer Basic)
            if module != 'Basic':
                score = module_scores.get(module, 0)  # Korrekte Modul-Scores aus der Session abrufen
                score_paragraph = Paragraph(f"<b>Modul-Score: {score} Punkte</b>", styles['Normal'])
                elements.append(score_paragraph)
                elements.append(Spacer(1, 12))

                # Bewertungstabelle hinzufügen
                if module == 'Express':
                    eval_data = [
                        ["Eignung", "Punkte", "Empfehlung"],
                        ["Gering", "-50 – 18", "Wirtschaftlich nicht darstellbar\nIndividuallösung erforderlich"],
                        ["Mittel", "19 – 35", "Eingeschränkt möglich\n(Bitte suchen Sie einen Experten auf)"],
                        ["Hoch", "36 – 60", "Gute Voraussetzungen für eine serielle Sanierung"]
                    ]
                elif module == 'Advanced':
                    eval_data = [
                        ["Kategorie", "Punktebereich", "Bewertung"],
                        ["Niedrig", "-100 – 50", "Wirtschaftlich nicht darstellbar\nIndividuallösung erforderlich"],
                        ["Mittel", "51 – 120", "Eingeschränkt möglich\n(Bitte suchen Sie einen Experten auf)"],
                        ["Hoch", "121 – 180", "Sehr gute Voraussetzungen für eine serielle Sanierung"]
                    ]

                eval_table = Table(eval_data, colWidths=[150, 100, 250])  # Einheitliche Spaltenbreiten
                eval_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                    ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 10),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('GRID', (0,0), (-1,-1), 1, colors.black)
                ]))
                elements.append(eval_table)
                elements.append(Spacer(1, 20))

            # Fragen/Antworten-Tabelle hinzufügen
            data = [["Frage", "Antwort"]] if module == 'Basic' else [["Frage", "Antwort", "Punkte"]]
            for qid, answer in all_answers[module].items():
                question_text = questions.get(qid).text if qid in questions else "Unbekannte Frage"
                answer_text = answer.get('text', '')
                score_text = str(answer.get('score', '-')) if module != 'Basic' else ""

                if module == 'Basic':
                    data.append([Paragraph(question_text, styles['Normal']), Paragraph(answer_text, styles['Normal'])])
                else:
                    data.append([Paragraph(question_text, styles['Normal']), Paragraph(answer_text, styles['Normal']), score_text])

            # Einheitliche Tabellenbreite für alle Module
            table_col_widths = [250, 250] if module == 'Basic' else [200, 200, 100]
            table = Table(data, colWidths=table_col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 36))

    # PDF generieren
    pdf.build(elements)
    pdf_buffer.seek(0)

    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Leitfaden_Steckbrief.pdf'

    return response

def populate_database():
    db.session.execute(Answer.__table__.delete())
    db.session.execute(Question.__table__.delete())
    db.session.commit()
    
    # Basic Modul
    q1 = Question(module="Basic", text="Projektname")
    q2 = Question(module="Basic", text="Standort")
    q3 = Question(module="Basic", text="Wer ist Eigentümer des Gebäudes?")
    a3_1 = Answer(question=q3, text="Privatperson", score=3)
    a3_2 = Answer(question=q3, text="Unternehmen", score=4)
    a3_3 = Answer(question=q3, text="Öffentliche Hand", score=2)
    a3_4 = Answer(question=q3, text="Gesellschaft", score=4)
    a3_5 = Answer(question=q3, text="Sonstiges", score=5)

    q4 = Question(module="Basic", text="Baujahr")
    a4_1 = Answer(question=q4, text="Vor 1950", score=6)
    a4_2 = Answer(question=q4, text="1950-1970", score=6)
    a4_3 = Answer(question=q4, text="1970-1990", score=8)
    a4_4 = Answer(question=q4, text="Nach 1990", score=9)

    q5 = Question(module="Basic", text="Gebäudetyp")
    a5_1 = Answer(question=q5, text="Wohngebäude", score=2)
    a5_2 = Answer(question=q5, text="Gewerbegebäude", score=3)
    a5_3 = Answer(question=q5, text="Gemischt genutztes Gebäude", score=4)
    a5_4 = Answer(question=q5, text="Sonstiges", score=6)

    q6 = Question(module="Basic", text="Zweck der Sanierung?")
    a6_1 = Answer(question=q6, text="Energetische Verbesserung", score=7)
    a6_2 = Answer(question=q6, text="Ästhetische Aufwertung", score=7)
    a6_3 = Answer(question=q6, text="Umnutzung", score=5)

   # Express Modul

    # Frage 7: Welche Form gleicht dem Gebäude?
    q7 = Question(module="Express", text="Welcher Form oder Kontur gleicht dein Gebäude am ehesten?", image="question_7.jpg")
    a7_1 = Answer(question=q7, text="Plattenbau", score=5, info_popup="Quelle Bild:https://pixabay.com/de/photos/mehrfamilienhaus-block-geb%C3%A4ude-haus-835817/")
    a7_2 = Answer(question=q7, text="Industrie oder Sporthallen", score=4, info_popup="Quelle Bild:https://www.holzbau-kappler.de/referenzen/fassadensanierung-turnhalle-wachtberg/ ")
    a7_3 = Answer(question=q7, text="Mehrfamilienhaus", score=4, info_popup="Quelle Bild:https://www.holzbau-kappler.de/referenzen/serielle-sanierung-in-idstein/")
    a7_4 = Answer(question=q7, text="Einfamilienhaus", score=0, info_popup="Quelle Bild:https://pixabay.com/de/photos/haus-neubau-eigenheim-wohung-66627/")

    # Frage 8: Stammt das Gebäude aus dem Zeitraum zwischen 1950 und 1979?
    q8 = Question(module="Express", text="Stammt das Gebäude aus dem Zeitraum zwischen 1950 und 1979?")
    a8_1 = Answer(question=q8, text="Ja", score=6)
    a8_2 = Answer(question=q8, text="Nein, aber zwischen 1980–1999", score=3)
    a8_3 = Answer(question=q8, text="Nein, vor 1950", score=0)
    a8_4 = Answer(question=q8, text="Nein, nach 2000", score=-20)

    # Frage 9: Ist die vorhandene Gebäudetechnik (Sanitär/Elektro) sanierungsbedürftig?
    q9 = Question(module="Express", text="Ist die vorhandene Gebäudetechnik (Sanitär/Elektro) sanierungsbedürftig?")
    a9_1 = Answer(question=q9, text="Ja", score=8)
    a9_2 = Answer(question=q9, text="Teilweise", score=4)
    a9_3 = Answer(question=q9, text="Nein", score=0)

    # Frage 10: Fällt das Gebäude unter den Denkmalschutz?
    q10 = Question(module="Express", text="Fällt das Gebäude unter den Denkmalschutz?")
    a10_1 = Answer(question=q10, text="Ja", score=-25)
    a10_2 = Answer(question=q10, text="Nein", score=12)

    # Frage 11: Verfolgt der Eigentümer langfristige Ziele mit dem Objekt?
    q11 = Question(module="Express", text="Verfolgt der Eigentümer langfristige Ziele mit dem Objekt?")
    a11_1 = Answer(question=q11, text="Ja, langfristige Nutzung", score=15, )
    a11_2 = Answer(question=q11, text="Unklar, keine klare Strategie erkennbar", score=2)
    a11_3 = Answer(question=q11, text="Kurzfristige Renditeorientierung", score=-15, info_popup="Ausrichtung auf finanzielle Gewinne oder Erträge.")

    # Frage 12: Gibt es Möglichkeiten/Potential für Aufstockungen oder Wohnraumerweiterungen?
    q12 = Question(module="Express", text="Gibt es Möglichkeiten/Potential für Aufstockungen oder Wohnraumerweiterungen?")
    a12_1 = Answer(question=q12, text="Ja", score=5)
    a12_2 = Answer(question=q12, text="Prüffähig", score=2)
    a12_3 = Answer(question=q12, text="Nein", score=0)

    # Frage 13: Gibt es Wiederholungsfaktoren im Gebäude oder den Gebäuden?
    q13 = Question(module="Express", text="Gibt es Wiederholungsfaktoren im Gebäude oder den Gebäuden?", info_popup="Wiederholung von Bauteilen wie Fenstern, Fassadenmodulen oder Grundrissen")
    a13_1 = Answer(question=q13, text="Ja", score=15, info_popup="(gleiche Gebäude)")
    a13_2 = Answer(question=q13, text="Teilweise", score=8, info_popup="(ähnliche Wohneinheiten oder Raumunterteilungen)")
    a13_3 = Answer(question=q13, text="Nein", score=0)

    # Frage 14: Welche Gebäudehöhe hat das Objekt?
    q14 = Question(module="Express", text="Welche Gebäudehöhe hat das Objekt?")
    a14_1 = Answer(question=q14, text="<13m", score=3)
    a14_2 = Answer(question=q14, text="13–22m", score=2)
    a14_3 = Answer(question=q14, text=">22m", score=-15)

    # Advanced Modul
    # Gebäudestruktur und Kubatur
    q15 = Question(module="Advanced", text="Ist die Gebäudeform klar und strukturiert?",subtitle="Gebäudestruktur und Kubatur")
    a15_1 = Answer(question=q15, text="Ja", score=4)
    a15_2 = Answer(question=q15, text="Teilweise", score=2)
    a15_3 = Answer(question=q15, text="Nein", score=0)

    q16 = Question(module="Advanced", text="Welche Gebäudehöhe hat das Objekt?",subtitle="Gebäudestruktur und Kubatur")
    a16_1 = Answer(question=q16, text="<13m", score=3)
    a16_2 = Answer(question=q16, text="13–22m", score=2)
    a16_3 = Answer(question=q16, text=">22m", score=-25)

    q17 = Question(module="Advanced", text="Anzahl der Vor-/Rücksprüngen?",subtitle="Gebäudestruktur und Kubatur", info_popup="Vorsprünge: Erker, Balkone oder auskragende Obergeschosse Rücksprünge: Loggien, zurückversetzte Eingänge und innenliegende Balkone")
    a17_1 = Answer(question=q17, text="Wenig", score=4, info_popup="(1-2)")
    a17_2 = Answer(question=q17, text="Mittel", score=2, info_popup="(2-5)")
    a17_3 = Answer(question=q17, text="Viel", score=0, info_popup="(5>10)")

    q18 = Question(module="Advanced", text="Vorhandene Balkone?",subtitle="Gebäudestruktur und Kubatur")
    a18_1 = Answer(question=q18, text="Keine", score=5)
    a18_2 = Answer(question=q18, text="Wenige, evtl. entfernbar", score=3)
    a18_3 = Answer(question=q18, text="Viele, evtl. entfernbar", score=2)
    a18_4 = Answer(question=q18, text="Viele, jedoch nicht entfernbar", score=0)

    q19 = Question(module="Advanced", text="Sind Dachüberstände vorhanden?",subtitle="Gebäudestruktur und Kubatur")
    a19_1 = Answer(question=q19, text="Keine", score=3)
    a19_2 = Answer(question=q19, text="Klein (<50cm)", score=2)
    a19_3 = Answer(question=q19, text="Groß (>50cm)", score=0)

    q20 = Question(module="Advanced", text="Wie sind die Grenzabstände des Gebäudes auf dem Grundstück?",subtitle="Gebäudestruktur und Kubatur")
    a20_1 = Answer(question=q20, text="Gut, großzügige Abstände", score=3)
    a20_2 = Answer(question=q20, text="Schwierig zu beurteilen", score=1)
    a20_3 = Answer(question=q20, text="Geringe Abstände", score=0)

    # Gebäudetyp und Nutzung
    q21 = Question(module="Advanced", text="Um welchen Gebäudetyp handelt es sich?",subtitle="Gebäudetyp und Nutzung")
    a21_1 = Answer(question=q21, text="Wohngebäude", score=6)
    a21_2 = Answer(question=q21, text="Öffentliches Gebäude (Schule/Sporthallen usw.)", score=4)
    a21_3 = Answer(question=q21, text="Gewerbe mit Umnutzungspotenzial", score=4, info_popup="Die Möglichkeit, bestehende Gebäude für neue Zwecke zu nutzen, z. B. die Umwandlung von Gewerbeimmobilien in Wohnraum.")
    a21_4 = Answer(question=q21, text="Gewerbe ohne Umnutzungspotential", score=-20)
    a21_5 = Answer(question=q21, text="Mischgebäude ohne Potenzial zur Umnutzung", score=-20)
    a21_6 = Answer(question=q21, text="Sonstige nicht aufgeführte Gebäudetypen", score=-10)

    q22 = Question(module="Advanced", text="Wie viele Wohneinheiten hat das Objekt?",subtitle="Gebäudetyp und Nutzung")
    a22_1 = Answer(question=q22, text=">5", score=8)
    a22_2 = Answer(question=q22, text="2–5", score=4)
    a22_3 = Answer(question=q22, text="<2", score=0)

    # Gebäudealter und Bauweise
    q23 = Question(module="Advanced", text="Baujahr des Gebäudes?",subtitle="Gebäudealter und Bauweise")
    a23_1 = Answer(question=q23, text="Vor 1950", score=0)
    a23_2 = Answer(question=q23, text="1950–1970", score=3)
    a23_3 = Answer(question=q23, text="1970–1990", score=1)
    a23_4 = Answer(question=q23, text="Nach 1990", score=-25)

    q24 = Question(module="Advanced", text="Sind Bestandsunterlagen vorhanden?",subtitle="Gebäudealter und Bauweise", info_popup="Sind z.B. Dokumente, die den baulichen Zustand, die Konstruktion und technische Details des Gebäudes festhalten.")
    a24_1 = Answer(question=q24, text="Ja", score=3)
    a24_2 = Answer(question=q24, text="Teilweise", score=1)
    a24_3 = Answer(question=q24, text="Nein", score=0)

    q25 = Question(module="Advanced", text="Gibt es Schadstoffbelastungen?",subtitle="Gebäudealter und Bauweise", info_popup="Schadstoffbelastungen bei alten Gebäuden beziehen sich auf gefährliche Materialien wie Asbest, PCB oder Schwermetalle, die gesundheitliche Risiken darstellen.")
    a25_1 = Answer(question=q25, text="Nein", score=4)
    a25_2 = Answer(question=q25, text="Ja", score=-5)
    a25_3 = Answer(question=q25, text="Keine Angabe möglich", score=0)

    q26 = Question(module="Advanced", text="Wurden bereits Teilsanierungen durchgeführt?",subtitle="Gebäudealter und Bauweise")
    a26_1 = Answer(question=q26, text="Nein", score=4)
    a26_2 = Answer(question=q26, text="Ja, dokumentiert", score=2)
    a26_3 = Answer(question=q26, text="Ja, undokumentiert", score=-2)

    # Statik und Tragfähigkeit
    q27 = Question(module="Advanced",
                text="Tragstruktur in gutem Zustand und geeignet für weitere Lastaufnahme?",subtitle="Statik und Tragfähigkeit")
    a27_1 = Answer(question=q27, text="Geeignet", score=8)
    a27_2 = Answer(question=q27, text="Ungeeignet/unbekannt", score=0)

    q28 = Question(module="Advanced", text="Liegt die Kellerdecke über Geländeoberkante?",subtitle="Statik und Tragfähigkeit" ,info_popup="Ist die Decke vom Keller höher als der Boden draußen")
    a28_1 = Answer(question=q28, text="Ja >50cm", score=4)
    a28_2 = Answer(question=q28, text="Knapp <50cm", score=2)
    a28_3 = Answer(question=q28, text="Ebenerdig/tiefer", score=0)

    q29 = Question(module="Advanced",
                text="Gibt es bei Ihrem Gebäude eine vorgehängte Fassade?",subtitle="Statik und Tragfähigkeit" ,info_popup="Eine vorgehängte Fassade ist eine Außenwandverkleidung, die mit Abstand zur tragenden Wand montiert wird, z. B. aus Glas oder Faserpaneelen, oft hinterlüftet.")
    a29_1 = Answer(question=q29, text="Nein", score=5)
    a29_2 = Answer(question=q29, text="Ja", score=0)
    a29_3 = Answer(question=q29, text=("Unbekannt (Kann ich nicht beurteilen)"), 
                score=2)
    # Technische Gebäudeausrüstung (TGA)
    q30 = Question(module="Advanced", text="Wie ist der Zustand bestehender Heizung/Wasserleitungen/Rohre?",subtitle="Technische Gebäudeausrüstung (TGA)")
    a30_1 = Answer(question=q30, text="Komplett erneuerungsbedürftig", score=6)
    a30_2 = Answer(question=q30, text="Sanierungsbedürftig", score=3)
    a30_3 = Answer(question=q30, text="Gut nutzbar", score=0)

    q31 = Question(module="Advanced", text="Zustand bestehender Elektroinstallation?",subtitle="Technische Gebäudeausrüstung (TGA)")
    a31_1 = Answer(question=q31, text="Komplett erneuerungsbedürftig", score=6)
    a31_2 = Answer(question=q31, text="Sanierungsbedürftig", score=3)
    a31_3 = Answer(question=q31, text="Gut", score=0)

    q32 = Question(module="Advanced", text="Gibt es zentrale TGA-Räume?",subtitle="Technische Gebäudeausrüstung (TGA)")
    a32_1 = Answer(question=q32, text="Ja", score=2)
    a32_2 = Answer(question=q32, text="Teilweise anpassbar", score=1)
    a32_3 = Answer(question=q32, text="Nein", score=0)

    q33 = Question(module="Advanced",text="Sind zentrale Flure oder Installationsschächte vorhanden,um Leitungen effizient zu verteilen?",subtitle="Technische Gebäudeausrüstung (TGA)")
    a33_1 = Answer(question=q33, text="Ja", score=4)
    a33_2 = Answer(question=q33, text="Teilweise, Anpassungen nötig", score=2)
    a33_3 = Answer(question=q33, text="Nein", score=0)

    # Energieeffizienz & Förderfähigkeit
    q34 = Question(module="Advanced",
                text="Aktuelle Energieeffizienzklasse des Gebäudes "
                        "(„Worst Performing Building“):",subtitle="Energieeffizienz & Förderfähigkeit")
    a34_1 = Answer(question=q34, text="Sehr schlecht (vor 1958)", score=6)
    a34_2 = Answer(question=q34, text="Mittelmäßig (1958–1979)", score=3)
    a34_3 = Answer(question=q34, text="Bereits saniert (+1980)", score=0)

    q35 = Question(module="Advanced",
                text="Welcher KfW-Effizienzhausstandard ist in Zukunft evtl. erreichbar?",subtitle="Energieeffizienz & Förderfähigkeit")
    a35_1 = Answer(question=q35, text="Problemlos EH55/EH40 möglich", score=6)
    a35_2 = Answer(question=q35, text="Schwierig EH55 knapp möglich", score=3)
    a35_3 = Answer(question=q35, text="Nicht erreichbar/extrem teuer", score=0)
    a35_4 = Answer(question=q35, text="Nicht beurteilbar", score=0)

    q36 = Question(module="Advanced", text="Wie würden Sie den aktuellen Energieverbrauch des Gebäudes einschätzen?",subtitle="Energieeffizienz & Förderfähigkeit")
    a36_1 = Answer(question=q36, text="Niedrig", score=-2)
    a36_2 = Answer(question=q36, text="Mittel", score=3)
    a36_3 = Answer(question=q36, text="Hoch", score=6)

    q37 = Question(module="Advanced", text="Gibt es Potential durch zusätzliche Maßnahmen, höhere Förderquoten zu erreichen?",subtitle="Energieeffizienz & Förderfähigkeit" ,info_popup="z.B. Photovoltaikanlagen")
    a37_1 = Answer(question=q37, text="Ja", score=2)
    a37_2 = Answer(question=q37, text="Eingeschränkt", score=1)
    a37_3 = Answer(question=q37, text="Nein", score=0)

    # Wirtschaftlichkeit
    q38 = Question(module="Advanced", text="Zusätzliche Kosten durch Rückbau alter Maßnahmen erwartet?",subtitle="Wirtschaftlichkeit" ,info_popup="Der Rückbau alter Maßnahmen im Baugewerbe bedeutet das Entfernen oder Demontieren veralteter Bauteile, schadstoffbelasteter Materialien oder Anbauten.")
    a38_1 = Answer(question=q38, text="Keine Kosten erwartet", score=2)
    a38_2 = Answer(question=q38, text="Zusatzkosten erwartet", score=0)

    q39 = Question(module="Advanced", text="Ist eine Komplettlösung durch ein Generalunternehmer möglich?",subtitle="Wirtschaftlichkeit" ,info_popup="Ein Generalunternehmer (GU) ist ein Bauunternehmen, das die vollständige Ausführung eines Bauprojekts übernimmt, einschließlich der Koordination von Subunternehmern, und das Bauwerk meist schlüsselfertig an den Auftraggeber übergibt.")
    a39_1 = Answer(question=q39, text="Ja", score=5)
    a39_2 = Answer(question=q39, text=("Teilweise möglich," " mit zusätzlicher Koordination"), score=2)
    a39_3 = Answer(question=q39, text=("Nein"), score=0)

    q40 = Question(module="Advanced", text="Gibt es Wiederholungsfaktoren im Gebäude oder den Gebäuden?",subtitle="Wirtschaftlichkeit")
    a40_1 = Answer(question=q40, text="Ja, das Objekt/die Objekte sind gleich aufgebaut", score=15)
    a40_2 = Answer(question=q40, text="Teilweise, die Stockwerke/Wohneinheiten sind ähnlich", score=10)
    a40_3 = Answer(question=q40, text="Nein, es gibt keine oder nur geringe Wiederholungsfaktoren", score=0)

    # Nachhaltigkeit und Baustoffqualität
    q41 = Question(module="Advanced", text="Möchten Sie Materialien mit geringen Rückbaukosten einsetzen?",subtitle="Nachhaltigkeit und Baustoffqualität")
    a41_1 = Answer(question=q41, text="Ja", score=2)
    a41_2 = Answer(question=q41, text="Teilweise", score=1)
    a41_3 = Answer(question=q41, text="Nein", score=0)

    q42 = Question(module="Advanced",
                text="Ist Ihnen eine nachhaltige Bauweise wichtig?",subtitle="Nachhaltigkeit und Baustoffqualität")
    a42_1 = Answer(question=q42, text="Ja, evtl. auch trotz Mehrkosten", score=2)
    a42_2 = Answer(question=q42, text="Teilweise", score=1)
    a42_3 = Answer(question=q42, text="Nein, Hauptsache kostengünstig", score=0)

    q43 = Question (module="Advanced",text="Soll durch die Sanierung eine deutliche Verbesserung der Wohnqualität erreicht werden?",subtitle="Nachhaltigkeit und Baustoffqualität")
    a43_1 = Answer(question=q43, text="Ja", score=2)
    a43_2 = Answer(question=q43, text="Teilweise", score=1)
    a43_3 = Answer(question=q43, text="Nein", score=0)

    # Ziele des Auftraggebers
    q44 = Question(module="Advanced",
                text="Ist eine schnelle Umsetzung der Sanierung gewünscht (kurze Bauzeit, geringe Mietausfälle)?", subtitle="Ziele des Auftraggebers")
    a44_1 = Answer(question=q44, text="Ja, ist gewünscht", score=2)
    a44_2 = Answer(question=q44, text=("Teilweise," " mit Einschränkungen"), score=1)
    a44_3 = Answer(question=q44,text=("Nein," " eher nicht nötig"), score=0)

    q45 = Question(module="Advanced",text="Ist es gewünscht," " dass die Mieter während der Sanierung im Objekt wohnen?", subtitle="Ziele des Auftraggebers")
    a45_1 = Answer(question=q45,text="Teilweise," " soweit wie möglich", score=2)
    a45_2 = Answer(question=q45,text="Ja," " dauerhaft", score=1)
    a45_3 = Answer(question=q45,text="Nein", score=0)

    q46 = Question(module="Advanced", text="Verfolgt der Eigentümer langfristige Ziele mit dem Objekt?", subtitle="Ziele des Auftraggebers")
    a46_1 = Answer(question=q46, text="Ja, langfristige Nutzung", score=15)
    a46_2 = Answer(question=q46, text="Unklar, keine klare Strategie erkennbar", score=2)
    a46_3 = Answer(question=q46, text="Kurzfristige Renditeorientierung ",score=-15)

    q47 = Question(module="Advanced",text=("Ist es gewünscht, den Wohnraum zu erweitern?"), subtitle="Ziele des Auftraggebers")
    a47_1 = Answer(question=q47, text="Ja, durch eine Aufstockung", score=4)
    a47_2 = Answer(question=q47, text="Teilweise, z.B. durch Integration von Balkonen in den Wohnraum", score=2)
    a47_3 = Answer(question=q47, text="Nein", score=0)

    # Füge alle Fragen und Antworten zur Datenbank hinzu
    db.session.add_all([
        # Basic Modul
        q1, q2, q3, q4, q5, q6,
        a3_1, a3_2, a3_3, a3_4, a3_5,
        a4_1, a4_2, a4_3, a4_4,
        a5_1, a5_2, a5_3, a5_4,
        a6_1, a6_2, a6_3,

        # Express Modul
        q7, q8, q9, q10, q11, q12, q13, q14,
        a7_1, a7_2, a7_3, a7_4,
        a8_1, a8_2, a8_3,
        a9_1, a9_2, a9_3,
        a10_1, a10_2,
        a11_1, a11_2, a11_3,
        a12_1, a12_2, a12_3,
        a13_1, a13_2, a13_3,
        a14_1, a14_2, a14_3,

        # Advanced Modul
        q15, q16, q17, q18, q19, q20, q21, q22, q23, q24, q25, q26, q27, q28, q29, q30, q31, q32, q33, q34, q35, q36, q37, q38, q39, q40, q41, q42, q43, q44, q45, q46, q47,
        a14_1, a14_2, a14_3,
        a15_1, a15_2, a15_3,
        a16_1, a16_2, a16_3,
        a17_1, a17_2, a17_3,
        a18_1, a18_2, a18_3,
        a19_1, a19_2, a19_3,
        a20_1, a20_2, a20_3, 
        a21_1, a21_2, a21_3,
        a22_1, a22_2, a22_3,
        a23_1, a23_2, a23_3,
        a24_1, a24_2, a24_3,
        a25_1, a25_2, a25_3,
        a26_1, a26_2,
        a27_1, a27_2, 
        a28_1, a28_2, a28_3,
        a29_1, a29_2, a29_3,
        a30_1, a30_2, a30_3,
        a31_1, a31_2, a31_3,
        a32_1, a32_2, a32_3,
        a33_1, a33_2, a33_3,
        a34_1, a34_2, a34_3,
        a35_1, a35_2,
        a36_1, a36_2, a36_3,
        a37_1, a37_2,
        a38_1, a38_2,
        a39_1, a39_2,a39_3,
        a40_1, a40_2,a40_3,
        a41_1, a41_2,a41_3,
        a42_1, a42_2,a42_3,
        a43_1, a43_2,a43_3,
        a44_1, a44_2,a44_3,
        a45_1, a45_2,a45_3,
        a46_1, a46_2,a46_3,     
        a47_1, a47_2,a47_3,
    
    ])

    db.session.commit()
    print("Datenbank erfolgreich befüllt!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        populate_database()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=True, use_reloader=False)
