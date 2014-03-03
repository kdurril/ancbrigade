from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
import django.core.validators
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required

from django.contrib import messages

from ancbrigadesite.models import Document
from ancbrigadesite.views import anc_data

import re

from tinymce.widgets import TinyMCE

def is_valid_anc(value):
	if not re.match("^[0-9][A-Z]$", value):
		raise ValidationError("An ANC is a number followed by an uppercase letter.")
	if value[0] not in anc_data or value[1] not in anc_data[value[0]]['ancs']:
		raise ValidationError("%s is not an ANC." % value)

	
class UploadDocumentForm(forms.Form):
	anc = forms.CharField(
		label="ANC",
		max_length=2,
		initial="9X",
		validators=[is_valid_anc],
		help_text="Enter the ANC number, like 3B, that this document is associated with.",
		widget=forms.TextInput(attrs={'class':'input-large'})
		)
	
	upload_type = forms.ChoiceField(
		choices=(("file", "Upload a File"), ("paste", "Paste Document"), ("url", "Paste a Link")),
		initial="file",
		label="Upload Method",
		)

	docfile = forms.FileField(
		label='File',
		help_text='Select the document to upload, or paste the contents of the document below.',
		required=False,
		)

	content = forms.CharField(
		label="Document",
		initial="",
		help_text="Copy and paste the contents of the document here.",
		widget=TinyMCE(),
		required=False,
		)

	url = forms.CharField(
		label="URL",
		max_length=256,
		initial="http://",
		help_text="Paste a link to the document. It should be a PDF file.",
		required=False,
		validators=[django.core.validators.URLValidator],
		)

	def clean_docfile(self):
		if "docfile" not in self.cleaned_data:
			raise forms.ValidationError("Select a file.")

def upload_document(request, anc="9X"):
	# Handle file upload
	if request.method == 'POST':
		
		form = UploadDocumentForm(request.POST, request.FILES)
	
		if form.is_valid() \
			and not (form.cleaned_data["upload_type"] == "file" and "docfile" not in request.FILES) \
			and not (form.cleaned_data["upload_type"] == "paste" and not form.cleaned_data["content"]) \
			and not (form.cleaned_data["upload_type"] == "url" and not form.cleaned_data["url"]):
			newdoc = Document()
			newdoc.anc = form.cleaned_data['anc']
			if form.cleaned_data["upload_type"] == "file":
				newdoc.set_document_content(request.FILES['docfile'])
			elif form.cleaned_data["upload_type"] == "paste":
				newdoc.set_document_content(form.cleaned_data["content"])
			elif form.cleaned_data["upload_type"] == "url":
				try:
					import urllib2
					req = urllib2.Request(form.cleaned_data["url"])
					req.add_unredirected_header('User-Agent', 'ANCBrigade.com') # some ANC websites require something like this
					req.add_unredirected_header('Accept', '*/*') # some ANC websites require this
					resp = urllib2.urlopen(req)
					if resp.code != 200: raise ValueError("URL returned an error.")

					mime_type = resp.info()["content-type"].split(";")[0].strip()
					if mime_type != "application/pdf": raise ValueError("Not a PDF: " + mime_type)
					content = resp.read()
					newdoc.set_document_content(content, mime_type=mime_type)
					newdoc.source_url = form.cleaned_data["url"]
				except Exception as e:
					# ugh, dup'd code
					return render_to_response(
						'ancbrigadesite/upload_document.html',
						{ 'form': form, 'url_error': str(e) },
						context_instance=RequestContext(request)
					)
			else:
				raise
			newdoc.save()
			# recent ANC documents
		    #documents = Document.objects.filter(anc=anc).order_by('-created')[0:10]
			messages.success(request, 'Document {doc_id} created.'.format(doc_id=newdoc.id))
			

			# Redirect to the document list after POST
			return HttpResponseRedirect(reverse('ancbrigadesite.backend_views.edit_document', args=[newdoc.id]))
	else:
		form = UploadDocumentForm() # A empty, unbound form
		form.fields['anc'].initial = anc

	return render_to_response(
		'ancbrigadesite/upload_document.html',
		{ 'form': form },
		context_instance=RequestContext(request)
	)

def edit_document(request, doc_id):
	class EditDocumentForm(forms.ModelForm):
		class Meta:
			model = Document

	doc = get_object_or_404(Document, id=doc_id)

	if request.method == "POST":
		form = EditDocumentForm(request.POST, instance=doc)
		if form.is_valid():
			# Save and redirect back to page.
			doc.save()
	        messages.success(request, 'Document {doc_id} updated.'.format(doc_id=doc_id))
	else:
		form = EditDocumentForm(instance=doc)
		
	# Make sure the document is ready for annotation.
	doc.populate_annotation_document()

	return render_to_response(
		'ancbrigadesite/edit_document.html',
		{
			'document': doc,
			'form': form,
			'storage_api_base_url':reverse('annotator.root')[0:-1], # chop off trailing slash 
		},
		context_instance=RequestContext(request)
	)

